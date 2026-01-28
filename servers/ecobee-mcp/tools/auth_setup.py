#!/usr/bin/env python3
"""
Ecobee Auth Setup Script

Helps generating the initial Refresh Token for the Ecobee integration.
"""

import sys
import time
import requests
import argparse

def setup_auth(api_key):
    print(f"Requesting PIN for API Key: {api_key}")
    
    # 1. Request PIN
    url = f"https://api.ecobee.com/authorize?response_type=ecobeePin&client_id={api_key}&scope=smartWrite"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"Error requesting PIN: {response.text}")
        sys.exit(1)
        
    data = response.json()
    ecobee_pin = data['ecobeePin']
    code = data['code']
    interval = data.get('interval', 30)
    expires_in = data.get('expires_in', 600)
    
    print("\n" + "="*50)
    print(f"AUTHORIZATION REQUIRED")
    print("="*50)
    print(f"1. Go to: https://www.ecobee.com/consumer/portal/apps")
    print(f"2. Log in to your Ecobee account")
    print(f"3. Click 'Add Application' (My Apps sidebar)")
    print(f"4. Enter this PIN: {ecobee_pin}")
    print(f"5. Click 'Validate' and then 'Authorize'")
    print("="*50)
    print(f"\nWaiting for authorization (polling every {interval}s)...")
    
    # 2. Poll for token
    start_time = time.time()
    while (time.time() - start_time) < expires_in:
        time.sleep(interval)
        
        token_url = f"https://api.ecobee.com/token?grant_type=ecobeePin&code={code}&client_id={api_key}"
        token_response = requests.post(token_url)
        
        if token_response.status_code == 200:
            tokens = token_response.json()
            print("\n" + "="*50)
            print("SUCCESS! AUTHENTICATION COMPLETE")
            print("="*50)
            print("\nAdd these to your .env file or docker-compose environment:\n")
            print(f"ECOBEE_API_KEY={api_key}")
            print(f"ECOBEE_REFRESH_TOKEN={tokens['refresh_token']}")
            print("\n(Access Token is short-lived and will be refreshed automatically using the Refresh Token)")
            return
            
        elif token_response.status_code != 200:
            # Check if it's just waiting
            err = token_response.json()
            if err.get('error') == 'authorization_pending':
                print(".", end="", flush=True)
                continue
            else:
                print(f"\nError polling for token: {token_response.text}")
                sys.exit(1)
                
    print("\nTimeout waiting for authorization. Please try again.")

def main():
    parser = argparse.ArgumentParser(description='Ecobee Auth Setup')
    parser.add_argument('api_key', help='Your Ecobee API Key (Client ID)')
    args = parser.parse_args()
    
    setup_auth(args.api_key)

if __name__ == "__main__":
    main()
