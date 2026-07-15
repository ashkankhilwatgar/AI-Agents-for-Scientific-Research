from tools.functional_evidence import download_pdf, download_pdfs_for_papers


pmid = "24036952"
path = download_pdf(pmid=pmid, pdf_dir="tools/functional_papers")
print(f"下载结果: {path}")

if path:
    import os
    size = os.path.getsize(path)
    print(f"文件大小: {size} bytes")
    with open(path, "rb") as f:
        header = f.read(5)
    print(f"文件头: {header}") 