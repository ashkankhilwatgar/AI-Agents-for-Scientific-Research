from demo.tools.functional_evidence import analyze_variant

def main():
    variant = "NM_022168.4:c.1641+1G>C"
    results = analyze_variant(variant=variant, pdf_path= "demo/test/pdfs", download_pdfs=True, max_pdf_downloads=None)
    for result in results["experiments"]:
        print(result)



if __name__ == "__main__":
    main()
    

