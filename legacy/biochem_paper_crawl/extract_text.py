#!/usr/bin/env python3
"""
Extract text from XML papers and save to TXT format.
Reads from data_new/papers/ and saves to data_new/paper_txt/

Filters out papers without substantial main content to save processing time.
"""

import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from tqdm import tqdm

from fix_formatting_v2 import fix_formatting


def has_main_content_xml(xml_file: Path, min_content_length: int = 100) -> bool:
    """
    Check if an XML file has substantial main content in the body.
    
    This is a quick check to filter out papers without full text before
    doing the expensive text extraction and formatting.
    
    Args:
        xml_file: Path to the XML file
        min_content_length: Minimum length of body text to be considered valid
    
    Returns:
        True if the paper has substantial main content, False otherwise
    """
    try:
        with open(xml_file, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        root = ET.fromstring(xml_content)
        
        # Check for body element
        body_elem = root.find('.//body')
        if body_elem is None:
            return False
        
        # Get all text from body (quick check, not formatted)
        body_text = "".join(body_elem.itertext())
        body_text = re.sub(r'\s+', ' ', body_text).strip()
        
        return len(body_text) >= min_content_length
        
    except Exception:
        # On error, assume it might be valid
        return True


def get_text(elem) -> str:
    """
    Extract text from an XML element, normalizing whitespace.
    
    This handles inline elements like <italic>, <xref>, etc. that can cause
    whitespace artifacts when using itertext().
    
    Args:
        elem: XML element to extract text from
        
    Returns:
        Cleaned text with normalized whitespace
    """
    if elem is None:
        return ""
    
    # Get all text including from child elements
    text = "".join(elem.itertext())
    
    # Normalize whitespace: replace any sequence of whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_section_text(section_elem) -> list:
    """
    Recursively extract text from a section element, including nested sections.
    
    Args:
        section_elem: XML element representing a section
        
    Returns:
        List of (title, content) tuples for this section and nested sections
    """
    sections = []
    
    # Get section title
    title_elem = section_elem.find('./title')
    section_title = get_text(title_elem)
    
    # Get direct paragraphs (not nested in subsections)
    paragraphs = []
    for child in section_elem:
        if child.tag == 'p':
            para_text = get_text(child)
            if para_text:
                paragraphs.append(para_text)
    
    # Add this section if it has content
    if section_title or paragraphs:
        sections.append((section_title, "\n\n".join(paragraphs)))
    
    # Process nested sections
    for subsec in section_elem.findall('./sec'):
        sections.extend(extract_section_text(subsec))
    
    return sections


def extract_text_from_xml(xml_file: Path) -> str:
    """Extract text from PMC XML file with section names."""
    try:
        with open(xml_file, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        # Parse XML
        root = ET.fromstring(xml_content)
        
        # Extract title
        title_elem = root.find('.//article-title')
        title = get_text(title_elem)
        
        # Extract abstract (may have sections too)
        abstract_parts = []
        abstract_elem = root.find('.//abstract')
        if abstract_elem is not None:
            # Check for sectioned abstract
            abstract_sections = abstract_elem.findall('./sec')
            if abstract_sections:
                for sec in abstract_sections:
                    sec_title = get_text(sec.find('./title'))
                    sec_content = " ".join(get_text(p) for p in sec.findall('.//p'))
                    if sec_title:
                        abstract_parts.append(f"{sec_title}: {sec_content}")
                    elif sec_content:
                        abstract_parts.append(sec_content)
            else:
                # Simple abstract without sections
                abstract_text = get_text(abstract_elem)
                if abstract_text:
                    abstract_parts.append(abstract_text)
        
        abstract = "\n\n".join(abstract_parts)
        
        # Extract body with section names
        body_parts = []
        body_elem = root.find('.//body')
        if body_elem is not None:
            # Get top-level sections
            top_sections = body_elem.findall('./sec')
            if top_sections:
                for sec in top_sections:
                    sections = extract_section_text(sec)
                    for sec_title, sec_content in sections:
                        if sec_title and sec_content:
                            body_parts.append(f"## {sec_title}\n\n{sec_content}")
                        elif sec_title:
                            body_parts.append(f"## {sec_title}")
                        elif sec_content:
                            body_parts.append(sec_content)
            else:
                # No sections, just get all paragraphs
                paragraphs = [get_text(p) for p in body_elem.findall('.//p')]
                body_parts = [p for p in paragraphs if p]
        
        body = "\n\n".join(body_parts)
        
        # Extract references section if present
        ref_list = root.find('.//ref-list')
        references = ""
        if ref_list is not None:
            refs = []
            for ref in ref_list.findall('.//ref'):
                ref_text = get_text(ref)
                if ref_text:
                    refs.append(ref_text)
            if refs:
                references = "\n".join(refs)
        
        # Combine into text format
        text_content = f"Title: {title}\n\n"
        text_content += f"Abstract:\n{abstract}\n\n"
        text_content += f"Main Content:\n{body}\n"
        if references:
            text_content += f"\nReferences:\n{references}\n"
        
        # Apply formatting fixes
        text_content = fix_formatting(text_content)
        
        return text_content
        
    except Exception as e:
        print(f"Error processing {xml_file.name}: {e}")
        return None

def main():
    """Extract text from all XML files."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract text from XML papers')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Force re-processing of existing files')
    parser.add_argument('-d', '--directory', type=str, default=None,
                        help='Input directory containing XML files (default: data_new/papers)')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='Output directory for TXT files (default: data_new/paper_txt)')
    parser.add_argument('-m', '--min-length', type=int, default=100,
                        help='Minimum length of main content in characters (default: 100)')
    parser.add_argument('--move-incomplete', type=str, default=None,
                        help='Move XMLs without main content to this subdirectory (e.g., "no_main_content")')
    parser.add_argument('--no-filter', action='store_true',
                        help='Disable filtering - process all XML files regardless of content')
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    papers_dir = Path(args.directory) if args.directory else script_dir / "data_new" / "papers"
    output_dir = Path(args.output) if args.output else script_dir / "data_new" / "paper_txt"
    
    if not papers_dir.exists():
        print(f"Error: {papers_dir} does not exist!")
        print("Please run fetch_xml.py first to download papers.")
        return
    
    # Get all XML files
    xml_files = list(papers_dir.rglob("*.xml"))
    total_xml = len(xml_files)
    print(f"Found {total_xml} XML files")
    
    # Filter XMLs without main content (unless disabled)
    if not args.no_filter:
        print(f"Filtering XMLs with minimum content length: {args.min_length} characters...")
        valid_xml_files = []
        incomplete_xml_files = []
        
        for xml_file in tqdm(xml_files, desc="Checking content"):
            if has_main_content_xml(xml_file, args.min_length):
                valid_xml_files.append(xml_file)
            else:
                incomplete_xml_files.append(xml_file)
        
        print(f"XMLs with main content: {len(valid_xml_files)}")
        print(f"XMLs without main content: {len(incomplete_xml_files)}")
        
        # Optionally move incomplete XMLs
        if args.move_incomplete and incomplete_xml_files:
            print(f"Moving {len(incomplete_xml_files)} incomplete XMLs to '{args.move_incomplete}'...")
            for xml_file in tqdm(incomplete_xml_files, desc="Moving incomplete"):
                try:
                    relative_path = xml_file.relative_to(papers_dir)
                    dest_path = papers_dir / args.move_incomplete / relative_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(xml_file), str(dest_path))
                except Exception as e:
                    tqdm.write(f"Error moving {xml_file}: {e}")
        
        xml_files = valid_xml_files
    
    print(f"Processing {len(xml_files)} XML files")
    if args.force:
        print("Force mode: re-processing all files")
    print("=" * 60)
    
    extracted = 0
    skipped = 0
    failed = 0
    
    for xml_file in tqdm(xml_files, desc="Extracting text"):
        # Get drug name from parent directory
        drug_name = xml_file.parent.name
        
        # Create output directory
        drug_output_dir = output_dir / drug_name
        drug_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Output file path
        output_file = drug_output_dir / f"{xml_file.stem}.txt"
        
        # Skip if already exists (unless force mode)
        if output_file.exists() and not args.force:
            skipped += 1
            continue
        
        # Extract text
        text_content = extract_text_from_xml(xml_file)
        
        if text_content:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text_content)
            extracted += 1
        else:
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Text extraction complete!")
    print(f"{'='*60}")
    print(f"Total XML files found:       {total_xml:,}")
    if not args.no_filter:
        print(f"XMLs with main content:      {len(xml_files):,}")
        print(f"XMLs filtered out:           {total_xml - len(xml_files):,}")
    print(f"Successfully extracted:      {extracted:,}")
    print(f"Skipped (already exist):     {skipped:,}")
    print(f"Failed:                      {failed:,}")
    print(f"Output directory: {output_dir.absolute()}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()












