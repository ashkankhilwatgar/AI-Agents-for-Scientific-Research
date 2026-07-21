from tools.vep import annotate_variant
import pytest

def test_annotate_variant():
    annotate_variant("NP_001263274.1:p.Glu173del")


if __name__ == "__main__":
    print(annotate_variant("NP_001263274.1:p.Glu173del"))