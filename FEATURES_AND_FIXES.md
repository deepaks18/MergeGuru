# MergeGuru GUI - Updated Features & Fixes

## What's Fixed

### 1. âœ… Multiple Filters Support
- You can now add **multiple filters sequentially**
- All filters are displayed in the "Add Filters" page (Stage 5)
- Each filter shows a summary of what it does
- Filters are **applied in order** to refine the data progressively

### 2. âœ… Dependent Filters (Smart Filter Options)
- When you add a **second filter**, it only shows values that exist in the **data after applying the first filter**
- **Example**: 
  - Add filter 1: Select only "India, USA" in the **Country** column
  - Add filter 2: When filtering by **City**, only cities from India and USA are shown
  - This prevents invalid/incomplete filter combinations

### 3. âœ… Export in Multiple Formats
The application now fully supports exporting in three formats:
- **CSV** (.csv) - Universal, lightweight, spreadsheet-compatible
- **Excel** (.xlsx) - Microsoft Excel format with formatting support
- **Parquet** (.parquet) - Columnar format, best for large datasets

### 4. âœ… "Done" Button Now Works
- The "Done âœ“" button in Stage 6 (Export) is now **enabled**
- You can proceed with or without running the export
- After successful export, completion is confirmed

---

## How to Use Multiple Filters with Dependent Options

### Step-by-Step Guide

1. **Stage 4: Select Folder & Validate Files**
   - Choose your data folder
   - All files will be validated

2. **Stage 5: Add Filters** (New improved experience)
   - Click **"+ Add Filter"** button
   - Select your first column (e.g., "Country")
   - Choose filter type: Category, Text, or Date
   - For Category: Select values you want to include/exclude
   - Click **"Add Filter"**

3. **Adding a Second Filter** (Dependent)
   - Click **"+ Add Filter"** again
   - Select your second column (e.g., "City")
   - â­ **Note**: The City list will ONLY show cities from the countries you selected
   - No invalid combinations possible!
   - Add more filters as needed

4. **Remove a Filter**
   - Each filter has a **âœ•** button to remove it
   - After removing, re-apply subsequent filters if needed

5. **Stage 6: Export**
   - Set output file path
   - **Choose export format**: CSV, Excel, or Parquet
   - Click **"â–¶ Run Export"** to apply filters and save
   - File is saved with all filters applied

---

## Installation & Setup

### Required Dependencies
```bash
pip install -r requirements.txt
```

**Core packages:**
- `pandas` - Data manipulation
- `openpyxl` - Excel file support

**Optional:**
- `pyarrow` - For Parquet export (installed in requirements.txt)
- `fastparquet` - Alternative to pyarrow for Parquet

### Run the Application
```bash
python main_gui.py
```

---

## Filter Types Explained

### 1. Category Filters
- Select from a list of unique values in the column
- **Operators:**
  - Include: Keep only selected values
  - Exclude: Remove selected values
- Works best with columns that have <200 unique values

### 2. Text Filters
- Filter by text patterns
- **Operators:**
  - Equals: Exact match
  - Not equals: Exclude exact match
  - Contains: Partial match (case-insensitive)
  - Starts with: Beginning of value
  - Include list: Paste comma-separated values (one or more match)
  - Exclude list: Paste comma-separated values (remove matches)

### 3. Date Filters
- Filter by date ranges
- **Operators:**
  - Equals: Exact date match
  - Before: Earlier than date (exclusive)
  - After: Later than date (exclusive)
  - Between: Date range (inclusive)
- Format: **YYYY-MM-DD** (e.g., 2026-03-15)

---

## Export Format Comparison

| Format | Use Case | File Size | Speed | Excel Compatible |
|--------|----------|-----------|-------|------------------|
| **CSV** | Quick sharing, simple data | Small | Fast | âœ… Yes |
| **Excel** | Professional reports, formatting | Medium | Medium | âœ… Yes |
| **Parquet** | Big data, analytics, compression | Smallest | Fastest | âŒ No (specialized tools) |

---

## Troubleshooting

### Issue: "Parquet import error"
**Solution**: Install pyarrow
```bash
pip install pyarrow
```

### Issue: Only first filter showing
**Fixed!** All filters now display properly in the list.

### Issue: "Done" button is greyed out
**Fixed!** Button is now enabled in the export stage.

### Issue: Second filter shows all values (not dependent)
**Fixed!** Filters are now dependent - second filter respects first filter selections.

### Issue: Export fails
1. Check output file path is writable
2. Ensure format matches file extension
3. Check the export log for specific error messages

---

## Features Summary

âœ… **Multi-source support** - Combine CSV & Excel files from one folder  
âœ… **Smart validation** - Automatic column structure verification  
âœ… **Multiple filters** - Layer filters to refine data progressively  
âœ… **Dependent filters** - Filter options respect previous selections  
âœ… **Three formats** - CSV, Excel, and Parquet export  
âœ… **Live progress** - See file-by-file processing in real-time  
âœ… **Dark theme** - Easy on the eyes, modern interface  
âœ… **Thread-safe** - Non-blocking file operations  

---

## Version Info
- **MergeGuru v1.1**
- Last Updated: April 4, 2026
- Python 3.7+

