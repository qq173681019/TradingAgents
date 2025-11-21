import json
import os
import glob
from datetime import datetime

def migrate_to_split_storage(max_stocks_per_file=200):
    """Migrate single large JSON file to split files."""
    
    base_file = 'data/comprehensive_stock_data.json'
    if not os.path.exists(base_file):
        print(f"File {base_file} not found. Nothing to migrate.")
        return

    print(f"Loading {base_file}...")
    try:
        with open(base_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load file: {e}")
        return

    stocks = {}
    if 'stocks' in data:
        stocks = data['stocks']
    elif 'data' in data:
        stocks = data['data']
    else:
        stocks = data # Assuming root is dict of stocks if not wrapped

    total_stocks = len(stocks)
    print(f"Found {total_stocks} stocks.")
    
    if total_stocks == 0:
        print("No stocks found.")
        return

    # Create index
    stock_index = {}
    
    # Split into chunks
    stock_codes = sorted(list(stocks.keys()))
    
    chunks = [stock_codes[i:i + max_stocks_per_file] for i in range(0, len(stock_codes), max_stocks_per_file)]
    
    print(f"Splitting into {len(chunks)} parts...")
    
    base_name = base_file.replace('.json', '')
    
    for i, chunk in enumerate(chunks):
        part_num = i + 1
        part_filename = f"{base_name}_part_{part_num}.json"
        
        part_data = {
            'last_updated': datetime.now().isoformat(),
            'total_stocks': len(chunk),
            'stocks': {}
        }
        
        for code in chunk:
            part_data['stocks'][code] = stocks[code]
            stock_index[code] = part_filename
            
        with open(part_filename, 'w', encoding='utf-8') as f:
            json.dump(part_data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {part_filename} with {len(chunk)} stocks.")

    # Save index
    index_file = 'data/stock_file_index.json'
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(stock_index, f, ensure_ascii=False, indent=2)
    print(f"Saved index to {index_file}")
    
    # Rename original file
    backup_file = base_file + '.bak'
    if os.path.exists(backup_file):
        os.remove(backup_file)
    os.rename(base_file, backup_file)
    print(f"Renamed original file to {backup_file}")
    
    print("Migration complete.")

if __name__ == "__main__":
    migrate_to_split_storage()
