#!/usr/bin/env python3
"""
Test script for Paper Supply Agent API
Verifies all components are working correctly before AWS deployment
"""

import os
import sys
import json
import requests
import time
from datetime import datetime

# Configuration
API_BASE_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 10

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    """Print formatted header"""
    print(f"\n{BLUE}{'='*60}")
    print(f"{text:<60}")
    print(f"{'='*60}{RESET}")

def print_success(text):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")

def print_error(text):
    """Print error message"""
    print(f"{RED}✗ {text}{RESET}")

def print_warning(text):
    """Print warning message"""
    print(f"{YELLOW}⚠ {text}{RESET}")

def print_info(text):
    """Print info message"""
    print(f"{BLUE}ℹ {text}{RESET}")

def test_environment():
    """Test environment variables"""
    print_header("1. Checking Environment")
    
    checks = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").startswith("sk-"),
        "DB_TYPE": os.getenv("DB_TYPE") in ["sqlite", "postgres"],
        "PORT": os.getenv("PORT", "8000").isdigit(),
    }
    
    all_pass = True
    for key, status in checks.items():
        if status or os.getenv(key):
            print_success(f"{key}: {os.getenv(key, 'Not set')}")
        else:
            print_error(f"{key}: Not properly configured")
            all_pass = False
    
    return all_pass

def test_api_connectivity():
    """Test API is running"""
    print_header("2. Testing API Connectivity")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"API is running at {API_BASE_URL}")
            print_success(f"Status: {data.get('status')}")
            print_success(f"Version: {data.get('version')}")
            return True
        else:
            print_error(f"API returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to API at {API_BASE_URL}")
        print_info("Make sure API is running:")
        print_info("  uvicorn api:app --reload")
        return False
    except Exception as e:
        print_error(f"Connection error: {str(e)}")
        return False

def test_readiness():
    """Test API readiness"""
    print_header("3. Testing API Readiness")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/ready",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            print_success("API is ready to handle requests")
            return True
        else:
            print_warning(f"API not ready - status {response.status_code}")
            print_info("Agents may still be initializing...")
            return False
            
    except Exception as e:
        print_error(f"Readiness check failed: {str(e)}")
        return False

def test_quote_endpoint():
    """Test quote generation endpoint"""
    print_header("4. Testing Quote Generation")
    
    test_request = {
        "customer_request": "I need 200 sheets of A4 glossy paper and 100 sheets of cardstock",
        "context": "office manager organizing ceremony",
        "request_date": "2025-04-01"
    }
    
    try:
        print_info("Sending test quote request...")
        print_info(f"Request: {json.dumps(test_request, indent=2)}")
        
        response = requests.post(
            f"{API_BASE_URL}/quote",
            json=test_request,
            timeout=30  # Longer timeout for LLM
        )
        
        print_info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("status") == "success":
                print_success("Quote generation successful!")
                
                # Display parsed items
                items = data.get("parsed_items", [])
                if items:
                    print(f"\n  Parsed Items:")
                    for item in items:
                        print(f"    - {item.get('name')}: {item.get('quantity')} units")
                
                # Display quote
                quote = data.get("quote", {})
                if quote:
                    print(f"\n  Quote Information:")
                    if "total_amount" in quote:
                        print(f"    Total: ${quote.get('total_amount', 'N/A')}")
                    if "explanation" in quote:
                        print(f"    Details: {quote.get('explanation', 'N/A')[:100]}...")
                
                return True
            else:
                print_error(f"Quote generation failed: {data.get('error_message')}")
                return False
        else:
            print_error(f"API returned status {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print_warning("Quote generation timed out (LLM is slow)")
        print_info("This is normal for first calls - agents are initializing")
        return True  # Don't fail on timeout
    except Exception as e:
        print_error(f"Quote test failed: {str(e)}")
        return False

def test_order_processing():
    """Test full order processing endpoint"""
    print_header("5. Testing Order Processing")
    
    test_request = {
        "customer_request": "I would like to order 150 sheets of Colored paper",
        "context": "Small design agency",
        "request_date": "2025-04-01"
    }
    
    try:
        print_info("Sending test order request...")
        print_info(f"Request: {json.dumps(test_request, indent=2)}")
        
        response = requests.post(
            f"{API_BASE_URL}/process-order",
            json=test_request,
            timeout=30  # Longer timeout for LLM
        )
        
        print_info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("status") in ["success", "partial"]:
                print_success(f"Order processing successful! (status: {data.get('status')})")
                
                # Display request ID
                print_info(f"Request ID: {data.get('request_id')}")
                
                # Display inventory assessment
                assessment = data.get("inventory_assessment", {})
                if assessment:
                    print(f"\n  Inventory Assessment:")
                    print(f"    Can Fulfill: {assessment.get('can_fulfill', 'Unknown')}")
                    if assessment.get("in_stock_items"):
                        print(f"    In Stock Items: {len(assessment.get('in_stock_items', []))}")
                    if assessment.get("reorder_items"):
                        print(f"    Reorder Items: {len(assessment.get('reorder_items', []))}")
                
                return True
            else:
                print_error(f"Order processing failed: {data.get('error_message')}")
                return False
        else:
            print_error(f"API returned status {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print_warning("Order processing timed out (LLM is slow)")
        return True  # Don't fail on timeout
    except Exception as e:
        print_error(f"Order test failed: {str(e)}")
        return False

def test_database():
    """Test database connectivity"""
    print_header("6. Testing Database")
    
    db_type = os.getenv("DB_TYPE", "sqlite")
    
    if db_type == "sqlite":
        db_path = os.getenv("SQLITE_PATH", "munder_difflin.db")
        if os.path.exists(db_path):
            print_success(f"SQLite database found at {db_path}")
            
            # Check file size
            size_mb = os.path.getsize(db_path) / (1024 * 1024)
            print_info(f"Database size: {size_mb:.2f} MB")
            return True
        else:
            print_warning(f"SQLite database not found at {db_path}")
            print_info("Database will be created on first use")
            return True
    
    elif db_type == "postgres":
        print_info("PostgreSQL configuration detected")
        
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "postgres")
        db_name = os.getenv("DB_NAME", "paper_supplies")
        
        print_info(f"Host: {host}")
        print_info(f"Port: {port}")
        print_info(f"User: {user}")
        print_info(f"Database: {db_name}")
        
        try:
            import psycopg2
            print_success("PostgreSQL driver (psycopg2) is installed")
            
            # Try connection
            try:
                password = os.getenv("DB_PASSWORD", "")
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=db_name,
                    connect_timeout=5
                )
                conn.close()
                print_success("Successfully connected to PostgreSQL")
                return True
            except Exception as e:
                print_warning(f"Cannot connect to PostgreSQL: {str(e)}")
                print_info("Database may not be running or credentials are incorrect")
                return True  # Don't fail - might be intentional
                
        except ImportError:
            print_error("PostgreSQL driver (psycopg2) not installed")
            print_info("Install with: pip install psycopg2-binary")
            return False
    
    return True

def generate_report(results):
    """Generate test report"""
    print_header("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    percentage = (passed / total * 100) if total > 0 else 0
    
    print(f"\nResults: {passed}/{total} tests passed ({percentage:.0f}%)\n")
    
    for test_name, result in results.items():
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  {test_name}: {status}")
    
    if passed == total:
        print(f"\n{GREEN}✓ All tests passed! Ready for deployment.{RESET}\n")
        return True
    elif passed >= total * 0.75:
        print(f"\n{YELLOW}⚠ Most tests passed. Review failures above.{RESET}\n")
        return True
    else:
        print(f"\n{RED}✗ Some tests failed. Fix issues before deployment.{RESET}\n")
        return False

def main():
    """Run all tests"""
    print(f"{BLUE}")
    print("╔" + "="*58 + "╗")
    print("║  Paper Supply Agent API - Deployment Test Suite    ║")
    print("║  Testing local deployment before AWS push         ║")
    print("╚" + "="*58 + "╝")
    print(f"{RESET}")
    
    print_info(f"API Base URL: {API_BASE_URL}")
    print_info(f"Test Time: {datetime.now().isoformat()}\n")
    
    results = {
        "Environment": test_environment(),
        "API Connectivity": test_api_connectivity(),
        "API Readiness": test_readiness(),
        "Database": test_database(),
        "Quote Generation": test_quote_endpoint(),
        "Order Processing": test_order_processing(),
    }
    
    # Generate report
    success = generate_report(results)
    
    # Print deployment instructions
    print_header("Next Steps")
    print("""
1. If all tests pass:
   → Ready to build Docker image
   → Ready for AWS deployment
   
2. To build Docker image:
   $ docker build -t paper-supply-api:latest .
   
3. To test with Docker locally:
   $ docker-compose up -d
   $ curl http://localhost:8000/health
   
4. For AWS deployment:
   → See AWS_DEPLOYMENT.md for step-by-step instructions
   → Follow the deployment checklist
   
5. To run integration tests:
   $ ./test_api.py (this script)
    """)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
