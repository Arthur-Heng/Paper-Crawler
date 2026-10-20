#!/usr/bin/env python3
"""
Fix formatting issues in existing txt files - Version 2.

This script is more aggressive about cleaning up split lines.
"""

import re
import sys
from pathlib import Path
from tqdm import tqdm


def fix_formatting(text: str) -> str:
    """
    Fix formatting issues in the text by aggressively joining split lines.
    
    Args:
        text: Input text with formatting issues
        
    Returns:
        Cleaned text with fixed formatting
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    # First pass: strip all leading/trailing whitespace and filter empty tab-only lines
    for line in lines:
        stripped = line.strip()
        # Keep empty lines for paragraph breaks, but skip lines that are just tabs/spaces
        if stripped or (not line.strip()):
            cleaned_lines.append(stripped)
    
    # Second pass: merge lines that should be together
    result_lines = []
    i = 0
    
    while i < len(cleaned_lines):
        current_line = cleaned_lines[i]
        
        # Keep section headers and empty lines as-is
        if not current_line or current_line in ['Title:', 'Abstract:', 'Main Content:', 'References:'] or \
           current_line.startswith('Title:'):
            result_lines.append(current_line)
            i += 1
            continue
        
        # Start building a content line
        content_parts = [current_line]
        i += 1
        
        # Look ahead and join continuation lines
        while i < len(cleaned_lines):
            next_line = cleaned_lines[i]
            
            # Stop at empty lines (paragraph breaks)
            if not next_line:
                break
            
            # Stop at section headers
            if next_line in ['Title:', 'Abstract:', 'Main Content:', 'References:'] or \
               next_line.startswith('Title:'):
                break
            
            # Check if this looks like a continuation that should be joined
            should_join = False
            
            # Join if line is very short and matches continuation patterns
            if len(next_line) <= 30:
                # Just a number (reference)
                if re.match(r'^\d+$', next_line):
                    should_join = True
                # Just punctuation
                elif next_line in [',', ', ', ').', ')', '(', '.', ';', ':']:
                    should_join = True
                # Comma followed by optional space
                elif re.match(r'^,\s*$', next_line):
                    should_join = True
                # Just punctuation and number like ", 2"
                elif re.match(r'^,\s*\d+$', next_line):
                    should_join = True
                # Short words that are likely italicized terms or subscripts
                elif re.match(r'^[A-Za-z]{1,6}$', next_line):
                    should_join = True
                # Subscript-like numbers
                elif re.match(r'^\d+$', next_line) and len(content_parts[-1]) > 10:
                    should_join = True
            
            if should_join:
                content_parts.append(next_line)
                i += 1
                continue
            
            # For longer lines, check if current content ends with incomplete sentence
            current_content = ' '.join(content_parts)
            # If ends with opening paren, continue
            if current_content.rstrip().endswith('('):
                content_parts.append(next_line)
                i += 1
                continue
            
            # Otherwise, this is a new paragraph
            break
        
        # Join the content parts
        merged = ' '.join(content_parts)
        
        # Clean up whitespace
        merged = re.sub(r'\s+', ' ', merged)
        
        # Fix reference patterns
        # Multiple iterations to handle cases like "( 1 , 2 , 3 )"
        for _ in range(3):
            merged = re.sub(r'\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', r'(\1, \2, \3)', merged)
            merged = re.sub(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)', r'(\1, \2)', merged)
        merged = re.sub(r'\(\s*(\d+)\s*\)', r'(\1)', merged)
        
        # Fix bracket patterns
        merged = re.sub(r'\[\s*(\d+)\s*\]', r'[\1]', merged)
        
        # Fix spacing around punctuation
        merged = re.sub(r'\s+([.,;:!?)])', r'\1', merged)
        merged = re.sub(r'([(])\s+', r'\1', merged)
        
        # Fix patterns like "word ." -> "word."
        merged = re.sub(r'([A-Za-z])\s+\.', r'\1.', merged)
        
        # Fix table and figure references
        merged = re.sub(r'Table\s+(\d+)', r'Table \1', merged)
        merged = re.sub(r'Fig\s*\.?\s*(\d+[A-Z]*)', r'Fig. \1', merged)
        merged = re.sub(r'Figure\s+(\d+)', r'Figure \1', merged)
        
        if merged.strip():
            result_lines.append(merged.strip())
    
    # Join and clean up
    result = '\n'.join(result_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result


def process_file(file_path: Path, dry_run: bool = False) -> bool:
    """
    Process a single txt file to fix formatting.
    
    Args:
        file_path: Path to the txt file
        dry_run: If True, don't actually modify files
        
    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_text = f.read()
        
        fixed_text = fix_formatting(original_text)
        
        if original_text == fixed_text:
            return False
        
        if not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_text)
        
        return True
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return False


def fix_all_files(paper_txt_dir: str, dry_run: bool = False, limit: int = None) -> tuple:
    """Fix formatting in all txt files."""
    base_path = Path(paper_txt_dir)
    
    if not base_path.exists():
        print(f"Error: Directory {paper_txt_dir} does not exist", file=sys.stderr)
        return 0, 0
    
    txt_files = list(base_path.rglob("*.txt"))
    
    if limit:
        txt_files = txt_files[:limit]
    
    total_files = len(txt_files)
    
    print(f"Found {total_files} txt files to process")
    if dry_run:
        print("DRY RUN MODE - No files will be modified")
    print("=" * 80)
    
    modified_count = 0
    
    for txt_file in tqdm(txt_files, desc="Fixing formatting", unit="file"):
        if process_file(txt_file, dry_run):
            modified_count += 1
    
    return total_files, modified_count


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix formatting issues in txt paper files (v2)')
    parser.add_argument('-d', '--directory', type=str, default=None,
                        help='Base directory containing paper txt files (default: data_new/paper_txt)')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='Dry run mode - report what would be changed without actually modifying')
    parser.add_argument('-l', '--limit', type=int, default=None,
                        help='Limit processing to first N files (for testing)')
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    
    if args.directory:
        paper_txt_dir = Path(args.directory)
    else:
        paper_txt_dir = script_dir / "data_new" / "paper_txt"
    
    print(f"Processing papers in: {paper_txt_dir}")
    print()
    
    total, modified = fix_all_files(str(paper_txt_dir), dry_run=args.dry_run, limit=args.limit)
    
    print()
    print("=" * 80)
    print("PROCESSING COMPLETE")
    print("=" * 80)
    print(f"Total txt files processed:   {total:,}")
    print(f"Files modified:              {modified:,}")
    print(f"Files unchanged:             {total - modified:,}")
    
    if total > 0:
        modified_rate = (modified / total) * 100
        print(f"Modification rate:           {modified_rate:.2f}%")


if __name__ == '__main__':
    main()

