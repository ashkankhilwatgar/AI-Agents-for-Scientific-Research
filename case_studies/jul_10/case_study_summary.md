# 7/10/26 Simon

---

Today while experimenting with the code I found a weakness with our current quesition1 evaluation script. Our previous question1.py evaluation script load the applied criterion from golden csv. However, the criterias in the golden csv may have strength suffix, but the criterions in our prediction output may not. 

For example, our prediction output maybe PS4, whereas the corresponding column in the golder csv (golden_df) maybe {PM2_supporting, PS4_MODERATE, BS3}. In that case, although our model correctly predict PS4, the evaluation script will still falsely claim that our pipeline is incorrect. In other words, think about our script to check whether prediction is correct: 

```python
criterion in gold_applied_lookup[vkey]
```
If criterion == "PS4" whereas the actual criterion in gold_applied_lookup is "PS4_MODERATE", the above boolean expression will evaluate to false, even though technically speaking it should evaluate to true. So I add a remove_strength function to prevent this from happening.

---

After doing that, I ran the question1 evaluation sript again, and here is the result: 

- accuracy: 0.944558521560575
- precision: 0.9107142857142857
- recall: 0.8571428571428571
- F1: 0.8831168831168831
- number of (variant, criterion) pairs scored: 487
- number of criteria that errored during evaluation: 1
- number of criteria with no gold label (curator silent): 0
- number of predicted criteria with unmatched/unknown variant: 1347
- number of whole-variant failures excluded: 0

Confusion Matrix (rows=actual applies, cols=predicted applies):

|             | Pred False | Pred True |
| -: | -: | -: |
| Actual False |  358 |    10 |
| Actual True  |    17  |   102 |




|Criterion        |        N  | Accuracy | Precision   |  Recall  |       F1 |
| -: | -: | -: | -: | -: | -: |
|BA1              |       48  |    1.000 |     1.000   |   1.000  |    1.000 |
|BP4              |       40  |    0.975 |     0.800   |   1.000  |    0.889 |
|BS1              |       48  |    0.979 |     0.900   |   1.000  |    0.947 |
|BS3              |       48  |    0.896 |     0.000   |   0.000  |    0.000 |
|PM1              |       38  |    1.000 |     1.000   |   1.000  |    1.000 |
|PM2_SUPPORTING   |       48  |    1.000 |     1.000   |   1.000  |    1.000 |
|PM4              |        1  |    1.000 |     1.000   |   1.000  |    1.000 |
|PM5              |       38  |    0.816 |     0.417   |   1.000  |    0.588 |
|PP3              |       40  |    0.975 |     1.000   |   0.941  |    0.970 |
|PS1              |       38  |    0.974 |     0.000   |   0.000  |    0.000 |
|PS3              |       48  |    0.833 |     0.000   |   0.000  |    0.000 |
|PS4              |       47  |    0.936 |     0.958   |   0.920  |    0.939 |
|PVS1             |        5  |    1.000 |     1.000   |   1.000  |    1.000 |

--- 

Overall, the performance are still pretty good, and Ashkan's conclusion in case_studies/jul_9/case_study_applied_only.ipynb still holds.

Some significant pattern is 
- BS3, PS3, PS1 zero precision, recall, and F1
- PM5 low performance
- BS3 and PS3 low performance (which is due to large amont of false negative. This may due to our current function_evidence tool's limited ability in retrieving relevant literatures.)

I did a case study on the first two significant observations. Here is the link to the first two observations:

- [BS3, PS3, PS1 Case Study](case_study_BS3_PS3_PS1.ipynb)
- [PM5 Case Study](case_study_PM5.ipynb)

---