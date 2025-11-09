#!/usr/bin/env python3

import json
import time
import requests
from pathlib import Path
from typing import List, Dict, Any

API_URL = "http://localhost:8000/ask"
QUERY_FILE = Path("data/validation/query-list.json")
OUTPUT_FILE = Path("data/validation/answer-list.json")
TIMEOUT = 60
RATE_LIMIT_DELAY = 2
SAVE_INTERVAL = 3

def load_queries() -> List[Dict[str, Any]]:
    """Load queries from query-list.json"""
    with open(QUERY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_results(results: List[Dict[str, Any]]):
    """Save results to answer-list.json"""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved results to {OUTPUT_FILE}")

def call_api(query: str) -> Dict[str, Any]:
    """
    Call the /ask endpoint with a query.
    
    Returns:
        Dict with response data or error information
    """
    start_time = time.time()
    
    try:
        response = requests.post(
            API_URL,
            json={"query": query},  # No message_history
            timeout=TIMEOUT
        )
        
        response_time_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "actual_answer": data.get("answer", ""),
                "citations": data.get("citations", []),
                "follow_up": data.get("follow_up"),
                "response_time_ms": response_time_ms,
                "success": True,
                "error": None
            }
        else:
            return {
                "actual_answer": None,
                "citations": None,
                "follow_up": None,
                "response_time_ms": response_time_ms,
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
            
    except requests.exceptions.Timeout:
        response_time_ms = int((time.time() - start_time) * 1000)
        return {
            "actual_answer": None,
            "citations": None,
            "follow_up": None,
            "response_time_ms": response_time_ms,
            "success": False,
            "error": f"Request timed out after {TIMEOUT}s"
        }
        
    except requests.exceptions.ConnectionError:
        response_time_ms = int((time.time() - start_time) * 1000)
        return {
            "actual_answer": None,
            "citations": None,
            "follow_up": None,
            "response_time_ms": response_time_ms,
            "success": False,
            "error": "Connection error - is the API running?"
        }
        
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        return {
            "actual_answer": None,
            "citations": None,
            "follow_up": None,
            "response_time_ms": response_time_ms,
            "success": False,
            "error": f"Error: {type(e).__name__}: {str(e)}"
        }

def main():
    """Main validation loop"""
    print("=" * 60)
    print("🧪 Query Validation Script")
    print("=" * 60)
    print(f"Query file: {QUERY_FILE}")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"API endpoint: {API_URL}")
    print("=" * 60)
    print()
    
    # Load queries
    queries = load_queries()
    print()
    
    # Process queries
    results = []
    total_queries = len(queries)
    successful = 0
    failed = 0
    total_time = 0
    
    start_overall = time.time()
    
    for idx, query_item in enumerate(queries, 1):
        sn = query_item.get("sn", idx)
        query = query_item.get("query", "")
        expected_answer = query_item.get("answer", "")
        layer = query_item.get("layer", "")
        file = query_item.get("file", "")
        
        print(f"[{idx}/{total_queries}] Processing query #{sn}...")
        print(f"❓ Query: {query[:80]}{'...' if len(query) > 80 else ''}")
        
        # Call API
        result = call_api(query)
        
        # Build result object
        result_obj = {
            "sn": sn,
            "query": query,
            "expected_answer": expected_answer,
            "layer": layer,
            "source_file": file,
            **result
        }
        
        results.append(result_obj)
        
        # Update stats
        if result["success"]:
            successful += 1
            print(f"✅ Success ({result['response_time_ms']}ms)")
            if result.get("citations"):
                print(f"Citations: {len(result['citations'])}")
        else:
            failed += 1
            print(f"❌ Failed: {result['error']}")
        
        total_time += result["response_time_ms"]
        
        print()
        
        # Save intermediate results
        if idx % SAVE_INTERVAL == 0:
            save_results(results)
        
        # Rate limiting (don't delay after last query)
        if idx < total_queries:
            print(f"⏳ Waiting {RATE_LIMIT_DELAY}s before next query...")
            time.sleep(RATE_LIMIT_DELAY)
            print()
    
    # Final save
    save_results(results)
    
    # Summary
    overall_time = time.time() - start_overall
    avg_time = total_time / total_queries if total_queries > 0 else 0
    
    print()
    print("=" * 60)
    print("Overall Statistics")
    print("=" * 60)
    print(f"Total queries: {total_queries}")
    print(f"✅ Successful: {successful} ({successful/total_queries*100:.1f}%)")
    print(f"❌ Failed: {failed} ({failed/total_queries*100:.1f}%)")
    print(f"Average response time: {avg_time:.0f}ms")
    print(f"Total time (including delays): {overall_time:.1f}s")
    print(f"Results saved to: {OUTPUT_FILE}")
    print("=" * 60)
    print()
    
    if failed > 0:
        print("Some queries failed. Check the output file for details.")
    else:
        print("All queries completed successfully!")

if __name__ == "__main__":
    main()
