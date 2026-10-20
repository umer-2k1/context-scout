"""Quick validation script — run this first to verify your API keys work.

Usage:
    export CONTEXT_DEV_API_KEY="ctxt_secret_..."
    python test_api.py
"""

import os
import json
import sys
from dotenv import load_dotenv

def main():
    load_dotenv()

    api_key = os.environ.get("CONTEXT_DEV_API_KEY")
    if not api_key:
        print("❌ Set CONTEXT_DEV_API_KEY in your .env file")
        sys.exit(1)

    from context.dev import ContextDev
    client = ContextDev(api_key=api_key)

    tests_passed = 0
    tests_failed = 0

    # Test 1: Scrape
    print("=" * 50)
    print("Test 1: web.scrape (context.dev homepage)")
    print("=" * 50)
    try:
        result = client.web.scrape(url="https://context.dev", formats={"markdown": True})
        d = result.model_dump()
        print(f"  ✅ Keys: {list(d.keys())}")
        md = d.get("markdown", d.get("data", {}).get("markdown", ""))
        if md:
            print(f"  ✅ Got {len(str(md))} chars of markdown")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        tests_failed += 1

    # Test 2: Brand
    print("\n" + "=" * 50)
    print("Test 2: brand.retrieve (stripe.com)")
    print("=" * 50)
    try:
        result = client.brand.retrieve(domain="stripe.com", type="by_domain")
        d = result.model_dump()
        print(f"  ✅ Keys: {list(d.keys())}")
        brand = d.get("brand", {}) if isinstance(d.get("brand"), dict) else {}
        name = brand.get("title") or d.get("name", "?")
        print(f"  ✅ Company: {name}")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        tests_failed += 1

    # Test 3: Extract competitors
    print("\n" + "=" * 50)
    print("Test 3: web.extract_competitors (stripe.com)")
    print("=" * 50)
    try:
        result = client.web.extract_competitors(domain="stripe.com", num_competitors=3)
        d = result.model_dump()
        print(f"  ✅ Keys: {list(d.keys())}")
        print(f"  ✅ Data preview: {json.dumps(d, default=str)[:300]}")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        tests_failed += 1

    # Test 4: News search
    print("\n" + "=" * 50)
    print("Test 4: news.search (Stripe)")
    print("=" * 50)
    try:
        result = client.news.search(
            search_by={"type": "natural_language", "query": "Stripe payments"},
            limit=3,
        )
        d = result.model_dump()
        print(f"  ✅ Keys: {list(d.keys())}")
        print(f"  ✅ Data preview: {json.dumps(d, default=str)[:300]}")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        tests_failed += 1

    # Test 5: Web search
    print("\n" + "=" * 50)
    print("Test 5: web.search")
    print("=" * 50)
    try:
        result = client.web.search(query="Stripe vs Square payments", num_results=3)
        d = result.model_dump()
        print(f"  ✅ Keys: {list(d.keys())}")
        print(f"  ✅ Data preview: {json.dumps(d, default=str)[:300]}")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        tests_failed += 1

    # Test 6: Web answers
    print("\n" + "=" * 50)
    print("Test 6: web.answers")
    print("=" * 50)
    try:
        result = client.web.answers(task="What is Stripe's main product?")
        d = result.model_dump()
        print(f"  ✅ Keys: {list(d.keys())}")
        print(f"  ✅ Data preview: {json.dumps(d, default=str)[:300]}")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        tests_failed += 1

    # Summary
    print("\n" + "=" * 50)
    print(f"Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 50)

    if tests_failed == 0:
        print("🎉 All tests passed! You're ready to run Context Scout.")
        print("\nNext steps:")
        print('  export OPENAI_API_KEY="sk-..."')
        print("  python -m context_scout.cli firecrawl.dev")
    else:
        print("⚠️  Some tests failed. Check your API key and try again.")


if __name__ == "__main__":
    main()
