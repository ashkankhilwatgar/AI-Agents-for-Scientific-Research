from tools.functional_evidence import analyze_variant, download_pdfs_for_papers, download_pdf
from pprint import pprint


def main():
    variant = "NM_001114753.3:c.1844C>T"
    results = analyze_variant(variant=variant)

    print(f"{"=" * 500}")
    print("results: ")
    print(results)
    print(f"{"=" * 500}")
    


if __name__ == "__main__":
    main()
    

