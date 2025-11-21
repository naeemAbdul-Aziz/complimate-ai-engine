# engine/regulation_manager.py
"""
Regulation Management for CompliMate AI Engine
============================================

This module handles loading, indexing, and managing multiple regulation documents
with persistent vector storage and metadata tracking.
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

from llama_index.core import VectorStoreIndex, Document
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.vector_stores.chroma import ChromaVectorStore
# Optional Pinecone support (loaded lazily)
try:
    from llama_index.vector_stores.pinecone import PineconeVectorStore  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PineconeVectorStore = None  # type: ignore
import chromadb
from chromadb.config import Settings as ChromaSettings
from pypdf import PdfReader

from config import settings
from utils import LoggerMixin
from utils.pdf_utils import extract_pdf_text
from engine.vector_store.provider import VectorStoreProvider


@dataclass
class RegulationMetadata:
    """Metadata for a regulation document."""
    file_path: str
    file_name: str
    category: str
    title: str
    effective_date: Optional[str] = None
    last_amended: Optional[str] = None
    file_size: int = 0
    file_hash: str = ""
    indexed_date: str = ""
    chunk_count: int = 0
    description: str = ""
    tags: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegulationMetadata':
        """Create from dictionary."""
        return cls(**data)


class RegulationManager(LoggerMixin):
    """Manages multiple regulation documents with persistent storage."""
    
    def __init__(self):
        # Vector store can be ChromaVectorStore or PineconeVectorStore; use broad typing
        self.vector_store: Optional[Any] = None
        self.regulation_index: Optional[VectorStoreIndex] = None
        self.regulations_metadata: Dict[str, RegulationMetadata] = {}
        self.metadata_file = settings.REGULATIONS_DIR / "regulations_metadata.json"
        self.using_persistent_storage = False
        # Rate limit / cooldown state
        self._last_rebuild_attempt: Optional[datetime] = None
        self._consecutive_rate_limits: int = 0
        self._cooldown_seconds_base: int = 30  # base cooldown after 429
        self._max_cooldown_seconds: int = 15 * 60  # cap at 15 minutes
        self._last_rebuild_result: Optional[Dict[str, Any]] = None
        self._last_rate_limit_error: Optional[str] = None
        
        # Initialize storage
        self._initialize_storage()
        self._load_metadata()
    
    def _initialize_storage(self) -> None:
        """Initialize vector storage via provider abstraction only."""
        try:
            provider = VectorStoreProvider()
            store = provider.get_vector_store()
            if store:
                self.vector_store = store
                self.using_persistent_storage = True
                self.logger.info("Vector store initialized via provider")
            else:
                self.logger.info("No vector store returned; using in-memory index")
        except Exception as e:
            self.logger.error(f"Failed to initialize vector store provider: {e}")
            self.logger.info("Proceeding with in-memory fallback")
    
    def _initialize_chroma(self) -> None:
        """Initialize ChromaDB persistent storage with robust '_type' error handling."""
        try:
            settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
            vector_store_path = str(settings.VECTOR_STORE_DIR)
            chroma_client = chromadb.PersistentClient(
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True)
            )
            collection = None
            try:
                collection = chroma_client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
                # Check for '_type' error in metadata
                meta = getattr(collection, 'metadata', {})
                if not meta or '_type' not in meta:
                    self.logger.warning("Collection metadata missing '_type', recreating collection...")
                    chroma_client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
                    collection = chroma_client.create_collection(
                        name=settings.CHROMA_COLLECTION_NAME,
                        metadata={"description": "Ghana legal regulations for compliance analysis", "_type": "collection"}
                    )
                    self.logger.info(f"Recreated ChromaDB collection: {settings.CHROMA_COLLECTION_NAME}")
                else:
                    self.logger.info(f"Using existing ChromaDB collection: {settings.CHROMA_COLLECTION_NAME}")
            except Exception as get_error:
                self.logger.warning(f"Could not get or use existing collection: {get_error}")
                try:
                    chroma_client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
                except Exception:
                    pass
                collection = chroma_client.create_collection(
                    name=settings.CHROMA_COLLECTION_NAME,
                    metadata={"description": "Ghana legal regulations for compliance analysis", "_type": "collection"}
                )
                self.logger.info(f"Created new ChromaDB collection: {settings.CHROMA_COLLECTION_NAME}")
            self.vector_store = ChromaVectorStore(chroma_collection=collection)
            self.using_persistent_storage = True
            self.logger.info(f"ChromaDB initialized successfully (persistent mode at {vector_store_path})")
        except Exception as e:
            self.logger.error(f"Failed to initialize ChromaDB: {e}")
            try:
                chroma_client = chromadb.Client(settings=ChromaSettings(anonymized_telemetry=False))
                collection = chroma_client.create_collection(
                    name=settings.CHROMA_COLLECTION_NAME,
                    metadata={"description": "Ghana legal regulations for compliance analysis"}
                )
                self.vector_store = ChromaVectorStore(chroma_collection=collection)
                self.using_persistent_storage = False
                self.logger.info("ChromaDB initialized successfully (in-memory fallback mode)")
                if self.using_persistent_storage is False:
                    self.logger.info("Using in-memory storage - clearing existing metadata to force re-indexing")
                    self.regulations_metadata = {}
                    self._save_metadata()
            except Exception as fallback_error:
                self.logger.error(f"Failed to initialize in-memory ChromaDB: {fallback_error}")
                raise
    
    def _initialize_pinecone(self) -> None:  # pragma: no cover
        """Deprecated: initialization is handled by VectorStoreProvider."""
        self.logger.warning("Direct Pinecone init deprecated; using VectorStoreProvider instead.")

    def _load_metadata(self) -> None:
        """Load regulations metadata from JSON file."""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    metadata_dict = json.load(f)
                    
                self.regulations_metadata = {
                    file_name: RegulationMetadata.from_dict(data)
                    for file_name, data in metadata_dict.items()
                }
                
                # If using in-memory storage, clear metadata to force re-indexing
                if not self.using_persistent_storage:
                    self.logger.info("Using in-memory storage - clearing existing metadata to force re-indexing")
                    self.regulations_metadata.clear()
                
                self.logger.info(f"Loaded metadata for {len(self.regulations_metadata)} regulations")
            else:
                self.logger.info("No existing metadata file found, starting fresh")
                
        except Exception as e:
            self.logger.error(f"Failed to load metadata: {e}")
            self.regulations_metadata = {}
    
    def _save_metadata(self) -> None:
        """Save regulations metadata to JSON file."""
        try:
            settings.REGULATIONS_DIR.mkdir(parents=True, exist_ok=True)
            
            metadata_dict = {
                file_name: metadata.to_dict()
                for file_name, metadata in self.regulations_metadata.items()
            }
            
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
                
            self.logger.info("Metadata saved successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to save metadata: {e}")
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF with OCR support for scanned documents."""
        try:
            # Use the OCR-enabled extraction from utils/pdf_utils.py
            text = extract_pdf_text(
                file_path,
                enable_ocr=getattr(settings, "ENABLE_PDF_OCR", True),
                ocr_lang=getattr(settings, "OCR_LANG", "eng"),
                min_alpha_ratio=getattr(settings, "PDF_TEXT_MIN_ALPHA_RATIO", 0.2),
                min_line_len=getattr(settings, "PDF_FILTER_MIN_LINE_LEN", 12),
                logger=self.logger,
            )
            return text.strip() if text else ""
            
        except Exception as e:
            self.logger.error(f"Failed to extract text from {file_path}: {e}")
            return ""
    
    def _extract_metadata_from_text(self, text: str, file_name: str) -> Dict[str, Any]:
        """Extract basic metadata from regulation text."""
        # Simple metadata extraction - can be enhanced with NLP
        metadata = {
            "title": file_name.replace(".pdf", "").replace("_", " ").title(),
            "description": f"Legal regulation document: {file_name}",
            "tags": []
        }
        
        # Look for common patterns in Ghana legal documents
        if "petroleum" in text.lower():
            metadata["tags"].append("petroleum")
        if "mining" in text.lower():
            metadata["tags"].append("mining")
        if "environmental" in text.lower():
            metadata["tags"].append("environmental")
        if "labor" in text.lower() or "labour" in text.lower():
            metadata["tags"].append("labor")
            
        return metadata
    
    def discover_regulation_files(self) -> List[Path]:
        """Discover all regulation files recursively in the regulations directory."""
        if not settings.REGULATIONS_DIR.exists():
            self.logger.warning(f"Regulations directory not found: {settings.REGULATIONS_DIR}")
            return []
        
        regulation_files = []
        # Use rglob to search recursively in subdirectories
        for file_path in settings.REGULATIONS_DIR.rglob("*.pdf"):
            if file_path.is_file():
                regulation_files.append(file_path)
        
        self.logger.info(f"Discovered {len(regulation_files)} regulation files")
        return regulation_files
    
    def should_reindex_file(self, file_path: Path) -> bool:
        """Check if a file needs to be reindexed."""
        file_name = file_path.name
        
        # Check if file is new
        if file_name not in self.regulations_metadata:
            return True
        
        # Check if file has been modified
        current_hash = self._calculate_file_hash(file_path)
        stored_metadata = self.regulations_metadata[file_name]
        
        return current_hash != stored_metadata.file_hash
    
    def index_regulation_file(self, file_path: Path, category: str = "general") -> RegulationMetadata:
        """Index a single regulation file."""
        try:
            self.logger.info(f"Indexing regulation file: {file_path}")
            
            # Extract text
            text = self._extract_pdf_text(file_path)
            if not text:
                raise ValueError(f"No text extracted from {file_path}")
            
            # Extract metadata
            auto_metadata = self._extract_metadata_from_text(text, file_path.name)
            
            # Create regulation metadata
            file_stats = file_path.stat()
            metadata = RegulationMetadata(
                file_path=str(file_path),
                file_name=file_path.name,
                category=category,
                title=auto_metadata["title"],
                file_size=file_stats.st_size,
                file_hash=self._calculate_file_hash(file_path),
                indexed_date=datetime.now().isoformat(),
                description=auto_metadata["description"],
                tags=auto_metadata["tags"]
            )
            
            # Create documents with metadata
            documents = self._create_documents_from_text(text, metadata)
            metadata.chunk_count = len(documents)
            
            # Add to index
            if self.regulation_index is None:
                if self.vector_store:
                    self.regulation_index = VectorStoreIndex.from_documents(
                        documents, vector_store=self.vector_store
                    )
                else:
                    self.regulation_index = VectorStoreIndex.from_documents(documents)
            else:
                # Add documents to existing index
                for doc in documents:
                    self.regulation_index.insert(doc)
            
            # Store metadata
            self.regulations_metadata[file_path.name] = metadata
            self._save_metadata()
            
            self.logger.info(f"Successfully indexed {file_path.name} ({len(documents)} chunks)")
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to index {file_path}: {e}")
            raise
    
    def _create_documents_from_text(self, text: str, metadata: RegulationMetadata) -> List[Document]:
        """Create LlamaIndex documents from text with chunking."""
        # Create main document
        main_doc = Document(
            text=text,
            doc_id=f"regulation_{metadata.file_name}",
            metadata={
                "file_name": metadata.file_name,
                "category": metadata.category,
                "title": metadata.title,
                "tags": metadata.tags,
                "source_type": "regulation",
                "file_path": metadata.file_path
            }
        )
        
        # Parse into chunks if text is large
        if len(text) > settings.CHUNK_SIZE:
            parser = SimpleNodeParser.from_defaults(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )
            nodes = parser.get_nodes_from_documents([main_doc])
            
            # Convert nodes back to documents
            documents = []
            for i, node in enumerate(nodes):
                doc_id = f"{main_doc.doc_id}_chunk_{i}"
                # Explicitly add IDs to metadata so they appear in the vector store
                node_metadata = node.metadata.copy()
                node_metadata["doc_id"] = doc_id
                node_metadata["document_id"] = main_doc.doc_id
                
                doc = Document(
                    text=node.get_content(),
                    doc_id=doc_id,
                    metadata=node_metadata
                )
                documents.append(doc)
            
            return documents
        else:
            return [main_doc]
    
    def rebuild_index(self, force: bool = False) -> Dict[str, Any]:
        """Rebuild the entire regulation index."""
        try:
            now = datetime.utcnow()
            # Cooldown check
            if self._last_rebuild_attempt and self._consecutive_rate_limits > 0:
                elapsed = (now - self._last_rebuild_attempt).total_seconds()
                cooldown = min(self._cooldown_seconds_base * (2 ** (self._consecutive_rate_limits - 1)), self._max_cooldown_seconds)
                if elapsed < cooldown and not force:
                    remaining = int(cooldown - elapsed)
                    self.logger.warning(
                        f"Skipping rebuild due to active cooldown after rate limits. Try again in ~{remaining}s"
                    )
                    return {
                        "status": "cooldown",
                        "cooldown_remaining_seconds": remaining,
                        "last_result": self._last_rebuild_result,
                        "rate_limit_errors": self._consecutive_rate_limits
                    }
            self._last_rebuild_attempt = now
            self.logger.info("Starting regulation index rebuild...")
            
            # Discover all regulation files
            regulation_files = self.discover_regulation_files()
            
            if not regulation_files:
                self.logger.warning("No regulation files found to index")
                return {"status": "no_files", "files_processed": 0}
            
            # Clear existing index if forcing rebuild
            if force:
                self.regulation_index = None
                self.regulations_metadata.clear()
            
            # Process each file
            processed_files = []
            skipped_files = []
            error_files = []
            
            for file_path in regulation_files:
                try:
                    if not force and not self.should_reindex_file(file_path):
                        skipped_files.append(file_path.name)
                        continue
                    
                    # Determine category
                    category = self._determine_category(file_path.name)
                    
                    # Index the file
                    metadata = self.index_regulation_file(file_path, category)
                    processed_files.append({
                        "file_name": metadata.file_name,
                        "category": metadata.category,
                        "chunks": metadata.chunk_count
                    })
                    
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "rate limit" in msg.lower() or "insufficient_quota" in msg:
                        self._consecutive_rate_limits += 1
                        self._last_rate_limit_error = msg
                        self.logger.error(
                            f"Rate limit related failure while processing {file_path.name}: {msg} (consecutive={self._consecutive_rate_limits})"
                        )
                    else:
                        # Reset rate limit counter on non-429 errors
                        self._consecutive_rate_limits = 0
                    self.logger.error(f"Failed to process {file_path}: {e}")
                    error_files.append({"file_name": file_path.name, "error": msg})
            
            result = {
                "status": "completed",
                "files_processed": len(processed_files),
                "files_skipped": len(skipped_files),
                "files_failed": len(error_files),
                "processed_files": processed_files,
                "skipped_files": skipped_files,
                "error_files": error_files,
                "total_regulations": len(self.regulations_metadata)
            }
            
            # Reset cooldown counters if success and at least one file processed
            if result["files_processed"] > 0 and result["files_failed"] == 0:
                self._consecutive_rate_limits = 0
                self._last_rate_limit_error = None

            self._last_rebuild_result = result
            self.logger.info(f"Index rebuild completed: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to rebuild index: {e}")
            raise
    
    def _determine_category(self, file_name: str) -> str:
        """Determine regulation category from filename."""
        file_name_lower = file_name.lower()
        
        for category, files in settings.REGULATION_CATEGORIES.items():
            if file_name in files:
                return category
        
        # Auto-categorize based on filename
        if "petroleum" in file_name_lower or "li_2204" in file_name_lower:
            return "petroleum"
        elif "mining" in file_name_lower:
            return "mining"
        elif "environmental" in file_name_lower or "environment" in file_name_lower:
            return "environmental"
        elif "labor" in file_name_lower or "labour" in file_name_lower:
            return "labor"
        else:
            return "general"
    
    def get_regulation_index(self) -> Optional[VectorStoreIndex]:
        """Get the current regulation index."""
        if self.regulation_index is None:
            self.logger.info("No regulation index found, initiating conditional rebuild...")
            # Skip auto rebuild if OpenAI not configured (would fail anyway)
            if not settings.OPENAI_API_KEY:
                self.logger.warning("Skipping rebuild: OPENAI_API_KEY not configured")
                return None
            result = self.rebuild_index()
            if result.get("status") == "cooldown":
                self.logger.warning("Rebuild skipped due to cooldown; index remains unavailable")
            elif result["files_processed"] == 0:
                self.logger.warning("No regulations were indexed")
        
        return self.regulation_index
    
    def get_regulations_info(self) -> Dict[str, Any]:
        """Get information about all indexed regulations."""
        return {
            "total_regulations": len(self.regulations_metadata),
            "categories": self._get_category_summary(),
            "regulations": [metadata.to_dict() for metadata in self.regulations_metadata.values()],
            "storage_type": "persistent" if self.vector_store else "in-memory",
            "last_updated": max(
                [metadata.indexed_date for metadata in self.regulations_metadata.values()],
                default="never"
            )
        }
    
    def _get_category_summary(self) -> Dict[str, int]:
        """Get summary of regulations by category."""
        summary = {}
        for metadata in self.regulations_metadata.values():
            category = metadata.category
            summary[category] = summary.get(category, 0) + 1
        return summary
    
    def get_regulation_by_category(self, category: str) -> List[RegulationMetadata]:
        """Get all regulations in a specific category."""
        return [
            metadata for metadata in self.regulations_metadata.values()
            if metadata.category == category
        ]

    def search_regulations(self, query: str, category: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Semantic search across indexed regulation chunks.

        Returns a list of matches with minimal metadata.
        Falls back gracefully if index is unavailable.
        """
        if limit <= 0:
            return []
        index = self.get_regulation_index()
        if not index:
            self.logger.warning("Search requested but regulation index unavailable")
            return []
        try:
            from llama_index.core.retrievers import VectorIndexRetriever
            from llama_index.core.schema import QueryBundle
            retriever = VectorIndexRetriever(index=index, similarity_top_k=limit)
            query_bundle = QueryBundle(query_str=query)
            results = retriever.retrieve(query_bundle)
            matches: List[Dict[str, Any]] = []
            for r in results:
                meta = r.node.metadata or {}
                if category and meta.get("category") != category:
                    continue
                matches.append({
                    "text": r.node.get_content(),
                    "score": r.score,
                    "file_name": meta.get("file_name"),
                    "category": meta.get("category"),
                    "title": meta.get("title"),
                    "tags": meta.get("tags", []),
                })
                if len(matches) >= limit:
                    break
            return matches
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
    
    def add_regulation_file(self, file_path: Path, category: str = "general", 
                           metadata_override: Optional[Dict[str, Any]] = None) -> RegulationMetadata:
        """Add a new regulation file to the index."""
        try:
            # Index the file
            metadata = self.index_regulation_file(file_path, category)
            
            # Apply metadata overrides if provided
            if metadata_override:
                for key, value in metadata_override.items():
                    if hasattr(metadata, key):
                        setattr(metadata, key, value)
                
                # Update stored metadata
                self.regulations_metadata[file_path.name] = metadata
                self._save_metadata()
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to add regulation file {file_path}: {e}")
            raise
    
    def remove_regulation(self, file_name: str) -> bool:
        """Remove a regulation from the index."""
        try:
            if file_name not in self.regulations_metadata:
                self.logger.warning(f"Regulation {file_name} not found in metadata")
                return False
            
            # Remove from metadata
            del self.regulations_metadata[file_name]
            self._save_metadata()
            
            # Note: For ChromaDB, we would need to rebuild the index to truly remove
            # This is a limitation we'll address in future versions
            self.logger.info(f"Regulation {file_name} removed from metadata")
            self.logger.warning("Index rebuild required to fully remove documents from vector store")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove regulation {file_name}: {e}")
            return False
    
    def force_clear_vector_store(self) -> bool:
        """Force clear vector store and metadata with enhanced error handling."""
        try:
            self.logger.info("Force clearing vector store and metadata...")
            
            # Clear the vector store collection
            if hasattr(self, 'vector_store') and self.vector_store:
                try:
                    # Get the underlying chroma collection
                    collection = self.vector_store._collection
                    
                    # Get the client and delete/recreate the collection
                    client = collection._client
                    try:
                        client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
                        self.logger.info("Deleted existing ChromaDB collection")
                    except Exception as delete_error:
                        self.logger.warning(f"Could not delete collection: {delete_error}")
                    
                    # Recreate the collection
                    new_collection = client.create_collection(
                        name=settings.CHROMA_COLLECTION_NAME,
                        metadata={"description": "Ghana legal regulations for compliance analysis", "_type": "collection"}
                    )
                    self.vector_store = ChromaVectorStore(chroma_collection=new_collection)
                    self.logger.info("Recreated ChromaDB collection")
                    
                except Exception as vs_error:
                    self.logger.error(f"Error clearing vector store: {vs_error}")
                    # Reinitialize completely
                    self._initialize_chroma()
            
            # Clear metadata
            self.regulations_metadata = {}
            self._save_metadata()
            
            # Clear index cache
            self.index = None
            
            self.logger.info("Vector store and metadata cleared successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to force clear vector store: {e}")
            return False