from tools.functional_evidence import analyze_variant

def main():
    variant = "NM_022168.4:c.1641+1G>C"
    results = analyze_variant(variant=variant)
    for result in results["experiments"]:
        print(result)



if __name__ == "__main__":
    main()
    

