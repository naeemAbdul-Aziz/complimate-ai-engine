# scripts/log_manager.py
"""
Log Management Utility for CompliMate AI Engine
==============================================

Utility script for managing log files, viewing logs, and maintaining log health.
"""

import os
import sys
import gzip
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class LogManager:
    """Utility class for managing CompliMate logs."""
    
    def __init__(self, log_directory: Optional[str] = None):
        self.log_dir = Path(log_directory) if log_directory else Path.cwd() / "logs"
        self.log_dir.mkdir(exist_ok=True, parents=True)
    
    def list_log_files(self) -> List[Path]:
        """List all log files in the log directory."""
        log_files = []
        for pattern in ["*.log", "*.log.*"]:
            log_files.extend(self.log_dir.glob(pattern))
        return sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Get statistics about log files."""
        log_files = self.list_log_files()
        total_size = sum(f.stat().st_size for f in log_files)
        
        stats = {
            "total_files": len(log_files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "log_directory": str(self.log_dir),
            "files": []
        }
        
        for log_file in log_files:
            file_stat = log_file.stat()
            stats["files"].append({
                "name": log_file.name,
                "size_mb": round(file_stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                "lines": self._count_lines(log_file)
            })
        
        return stats
    
    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a log file."""
        try:
            if file_path.suffix == '.gz':
                with gzip.open(file_path, 'rt') as f:
                    return sum(1 for _ in f)
            else:
                with open(file_path, 'r') as f:
                    return sum(1 for _ in f)
        except Exception:
            return 0
    
    def tail_log(self, log_file: str, lines: int = 50) -> List[str]:
        """Get the last N lines from a log file."""
        log_path = self.log_dir / log_file
        if not log_path.exists():
            return [f"Log file {log_file} not found"]
        
        try:
            with open(log_path, 'r') as f:
                all_lines = f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            return [f"Error reading log file: {e}"]
    
    def search_logs(self, pattern: str, log_file: Optional[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """Search for a pattern in log files."""
        results = []
        
        if log_file:
            log_files = [self.log_dir / log_file]
        else:
            log_files = [f for f in self.list_log_files() if f.suffix in ['.log', '']]
        
        for log_file_path in log_files:
            if not log_file_path.exists():
                continue
                
            try:
                with open(log_file_path, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        if pattern.lower() in line.lower():
                            results.append({
                                "file": log_file_path.name,
                                "line_number": line_num,
                                "content": line.strip(),
                                "timestamp": self._extract_timestamp(line)
                            })
                            
                            if len(results) >= max_results:
                                return results
            except Exception as e:
                results.append({
                    "file": log_file_path.name,
                    "error": f"Could not read file: {e}"
                })
        
        return results
    
    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from log line."""
        try:
            # Try to extract ISO format timestamp
            if " | " in line:
                parts = line.split(" | ")
                if parts:
                    return parts[0].strip()
            elif " - " in line:
                parts = line.split(" - ")
                if parts:
                    return parts[0].strip()
        except Exception:
            pass
        return None
    
    def clean_old_logs(self, days_to_keep: int = 30) -> Dict[str, Any]:
        """Clean up log files older than specified days."""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        cleaned_files = []
        total_freed_mb = 0
        
        for log_file in self.list_log_files():
            file_modified = datetime.fromtimestamp(log_file.stat().st_mtime)
            
            if file_modified < cutoff_date:
                file_size_mb = log_file.stat().st_size / (1024 * 1024)
                try:
                    log_file.unlink()
                    cleaned_files.append({
                        "name": log_file.name,
                        "size_mb": round(file_size_mb, 2),
                        "modified": file_modified.isoformat()
                    })
                    total_freed_mb += file_size_mb
                except Exception as e:
                    cleaned_files.append({
                        "name": log_file.name,
                        "error": f"Failed to delete: {e}"
                    })
        
        return {
            "cleaned_files": len([f for f in cleaned_files if "error" not in f]),
            "total_freed_mb": round(total_freed_mb, 2),
            "files": cleaned_files
        }
    
    def analyze_error_patterns(self, log_file: Optional[str] = None) -> Dict[str, Any]:
        """Analyze error patterns in log files."""
        error_patterns = {}
        total_errors = 0
        
        if log_file:
            log_files = [self.log_dir / log_file]
        else:
            log_files = [f for f in self.list_log_files() if f.suffix in ['.log', '']]
        
        for log_file_path in log_files:
            if not log_file_path.exists():
                continue
            
            try:
                with open(log_file_path, 'r') as f:
                    for line in f:
                        if any(level in line.upper() for level in ['ERROR', 'CRITICAL', 'EXCEPTION']):
                            total_errors += 1
                            
                            # Extract error type
                            error_type = "Unknown"
                            if "Exception:" in line:
                                error_type = line.split("Exception:")[0].split()[-1] + "Exception"
                            elif "Error:" in line:
                                error_type = line.split("Error:")[0].split()[-1] + "Error"
                            elif "CRITICAL" in line.upper():
                                error_type = "Critical"
                            elif "ERROR" in line.upper():
                                error_type = "Error"
                            
                            if error_type not in error_patterns:
                                error_patterns[error_type] = {
                                    "count": 0,
                                    "first_seen": None,
                                    "last_seen": None,
                                    "examples": []
                                }
                            
                            pattern = error_patterns[error_type]
                            pattern["count"] += 1
                            
                            timestamp = self._extract_timestamp(line)
                            if timestamp:
                                if not pattern["first_seen"] or timestamp < pattern["first_seen"]:
                                    pattern["first_seen"] = timestamp
                                if not pattern["last_seen"] or timestamp > pattern["last_seen"]:
                                    pattern["last_seen"] = timestamp
                            
                            # Keep up to 3 examples
                            if len(pattern["examples"]) < 3:
                                pattern["examples"].append(line.strip())
                                
            except Exception as e:
                continue
        
        return {
            "total_errors": total_errors,
            "unique_patterns": len(error_patterns),
            "patterns": dict(sorted(
                error_patterns.items(), 
                key=lambda x: x[1]["count"], 
                reverse=True
            ))
        }


def main():
    """Main CLI interface for log management."""
    parser = argparse.ArgumentParser(description="CompliMate AI Engine Log Manager")
    parser.add_argument("--log-dir", type=str, help="Log directory path")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show log file statistics")
    
    # Tail command
    tail_parser = subparsers.add_parser("tail", help="Show last lines from a log file")
    tail_parser.add_argument("file", help="Log file name")
    tail_parser.add_argument("--lines", type=int, default=50, help="Number of lines to show")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for pattern in logs")
    search_parser.add_argument("pattern", help="Search pattern")
    search_parser.add_argument("--file", help="Specific log file to search")
    search_parser.add_argument("--max-results", type=int, default=100, help="Maximum results")
    
    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Clean old log files")
    clean_parser.add_argument("--days", type=int, default=30, help="Days to keep")
    
    # Errors command
    errors_parser = subparsers.add_parser("errors", help="Analyze error patterns")
    errors_parser.add_argument("--file", help="Specific log file to analyze")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    log_manager = LogManager(args.log_dir)
    
    if args.command == "stats":
        stats = log_manager.get_log_stats()
        print(f"\n📊 Log Statistics")
        print(f"================")
        print(f"Directory: {stats['log_directory']}")
        print(f"Total Files: {stats['total_files']}")
        print(f"Total Size: {stats['total_size_mb']} MB")
        print(f"\n📄 File Details:")
        for file_info in stats['files']:
            print(f"  {file_info['name']:20} | {file_info['size_mb']:8.2f} MB | {file_info['lines']:8} lines")
    
    elif args.command == "tail":
        lines = log_manager.tail_log(args.file, args.lines)
        print(f"\n📋 Last {args.lines} lines from {args.file}:")
        print("=" * 60)
        for line in lines:
            print(line.rstrip())
    
    elif args.command == "search":
        results = log_manager.search_logs(args.pattern, args.file, args.max_results)
        print(f"\n🔍 Search results for '{args.pattern}':")
        print("=" * 60)
        for result in results:
            if "error" in result:
                print(f"❌ {result['file']}: {result['error']}")
            else:
                print(f"📍 {result['file']}:{result['line_number']} | {result['content']}")
    
    elif args.command == "clean":
        result = log_manager.clean_old_logs(args.days)
        print(f"\n🧹 Cleanup Results (keeping last {args.days} days):")
        print("=" * 60)
        print(f"Files cleaned: {result['cleaned_files']}")
        print(f"Space freed: {result['total_freed_mb']} MB")
        
        if result['files']:
            print("\nCleaned files:")
            for file_info in result['files']:
                if "error" in file_info:
                    print(f"  ❌ {file_info['name']}: {file_info['error']}")
                else:
                    print(f"  ✅ {file_info['name']} ({file_info['size_mb']} MB)")
    
    elif args.command == "errors":
        analysis = log_manager.analyze_error_patterns(args.file)
        print(f"\n🚨 Error Analysis:")
        print("=" * 60)
        print(f"Total errors: {analysis['total_errors']}")
        print(f"Unique patterns: {analysis['unique_patterns']}")
        
        print(f"\n🔍 Error Patterns (by frequency):")
        for error_type, data in analysis['patterns'].items():
            print(f"\n  {error_type}: {data['count']} occurrences")
            if data['first_seen']:
                print(f"    First seen: {data['first_seen']}")
            if data['last_seen']:
                print(f"    Last seen: {data['last_seen']}")
            if data['examples']:
                print(f"    Example: {data['examples'][0][:100]}...")


if __name__ == "__main__":
    main()