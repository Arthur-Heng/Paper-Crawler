#!/bin/bash

# Full data collection pipeline with chemistry filters
# Saves all data to data_new/ directory

echo "=============================================================================="
echo "FULL DATA COLLECTION WITH CHEMISTRY FILTERS"
echo "=============================================================================="
echo ""
echo "Output directory: data_new/"
echo "  - data_new/pmcids/    : PMC IDs with metadata"
echo "  - data_new/papers/    : Full-text XML papers"
echo "  - data_new/paper_txt/ : Extracted text files"
echo ""
echo "=============================================================================="

# Step 1: Fetch PMCIDs with chemistry filters
echo ""
echo "STEP 1: Fetching PMCIDs with chemistry filters..."
echo "----------------------------------------------------------------------------"
python3 fetch_pmcid.py
if [ $? -ne 0 ]; then
    echo "Error in Step 1!"
    exit 1
fi

echo ""
echo "✓ Step 1 complete!"
echo ""

# Step 2: Download papers (XML)
echo "STEP 2: Downloading full-text papers (XML)..."
echo "----------------------------------------------------------------------------"
python3 fetch_xml.py
if [ $? -ne 0 ]; then
    echo "Error in Step 2!"
    exit 1
fi

echo ""
echo "✓ Step 2 complete!"
echo ""

# Step 3: Extract text
echo "STEP 3: Extracting text from papers..."
echo "----------------------------------------------------------------------------"
python3 extract_text.py
if [ $? -ne 0 ]; then
    echo "Error in Step 3!"
    exit 1
fi

echo ""
echo "✓ Step 3 complete!"
echo ""

# Summary
echo "=============================================================================="
echo "COLLECTION COMPLETE!"
echo "=============================================================================="
echo ""
echo "Data saved to:"
echo "  - data_new/pmcids/    : $(find data_new/pmcids -name "*.json" 2>/dev/null | wc -l) JSON files"
echo "  - data_new/papers/    : $(find data_new/papers -name "*.xml" 2>/dev/null | wc -l) XML files"
echo "  - data_new/paper_txt/ : $(find data_new/paper_txt -name "*.txt" 2>/dev/null | wc -l) TXT files"
echo ""
echo "Next step: Generate QA pairs with qa_data_filtered.py"
echo "=============================================================================="












