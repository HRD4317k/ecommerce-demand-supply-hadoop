# References

Everything this project builds on. "Checked" means the page was opened while building the project; the rest are
standard works cited from knowledge, so check them before quoting in a report.

## Data

1. **Olist.** *Brazilian E-Commerce Public Dataset by Olist.* Kaggle, listing `olistbr/brazilian-ecommerce`. About 100,000
   anonymised marketplace orders placed in Brazil, 2016-2018. Licence: CC BY-NC-SA 4.0 (attribution, non-commercial,
   share-alike); the licence was read on a course page that reproduces the Kaggle description
   (<https://scripts-and-tables.github.io/daa/data/>) because Kaggle itself could not be opened from the workspace, so re-check
   it on the Kaggle page. **Please cite Olist as the data source in anything you hand in.**
2. **GitHub mirror used for development:** <https://github.com/iiaauu456-boop/brazilian-olist-e-commerce-dataset>
   (commit `b93633e`), "a direct 9 CSV copy" of the Kaggle files; row counts match the official release (see `docs/DATA.md`).
   Not an official source: prefer the Kaggle download when you can.

## Apache Hadoop and MapReduce

3. J. Dean and S. Ghemawat. *MapReduce: Simplified Data Processing on Large Clusters.* OSDI 2004. The programming model
   behind every job here (map, shuffle, reduce, combiners).
4. T. White. *Hadoop: The Definitive Guide*, 4th ed. O'Reilly, 2015. Streaming, distributed cache, reduce-side and map-side joins.
5. J. Lin and C. Dyer. *Data-Intensive Text Processing with MapReduce.* Morgan & Claypool, 2010. The "pairs" pattern and
   order inversion used for the bundle-mining jobs.
6. Apache Software Foundation. *Hadoop Streaming* (documentation): <https://hadoop.apache.org/docs/stable/hadoop-streaming/HadoopStreaming.html>
   (options `-files`, `-cmdenv`, `-combiner`; the `mapreduce_map_input_file` variable). Not opened in this session (blocked); standard documentation URL.
7. Apache Software Foundation. *Apache Hive* language manual, <https://hive.apache.org>. Reference for the `hive/` scripts.

## Forecasting (idea 1)

8. R. J. Hyndman and G. Athanasopoulos. *Forecasting: Principles and Practice*, 3rd ed. OTexts, 2021, <https://otexts.com/fpp3/>.
   Rolling-origin evaluation, naive and seasonal-naive benchmarks, moving averages, damped trend.
9. R. J. Hyndman and A. B. Koehler. Another look at measures of forecast accuracy. *International Journal of Forecasting* 22(4), 2006.
   Why scale-free error measures such as WAPE are preferred on intermittent, small-volume series.
10. R. G. Brown. *Statistical Forecasting for Inventory Control.* McGraw-Hill, 1959. Origin of exponential smoothing for inventory.

## Inventory, reorder points and service levels (ideas 2, 3)

11. E. A. Silver, D. F. Pyke and D. J. Thomas. *Inventory and Production Management in Supply Chains*, 4th ed. CRC Press, 2017.
    (s, S) policies and the safety-stock formula with demand and lead-time variability.
12. S. Nahmias and T. L. Olsen. *Production and Operations Analysis*, 7th ed. Waveland Press, 2015. Service levels and the normal approximation.
13. S. Chopra and P. Meindl. *Supply Chain Management: Strategy, Planning, and Operation.* Pearson. Cycle service level, safety stock,
    supplier reliability.

## Optimisation (idea 4)

14. G. B. Dantzig. Application of the simplex method to a transportation problem. In *Activity Analysis of Production and Allocation*,
    Wiley, 1951. The transportation problem solved per SKU.
15. Q. Huangfu and J. A. J. Hall. Parallelizing the dual revised simplex method. *Mathematical Programming Computation* 10(1),
    119-142, 2018, doi:10.1007/s12532-017-0130-5. The HiGHS solver used through SciPy `linprog`. Checked (<https://webhomes.maths.ed.ac.uk/hall/HuHa13/>).
16. SciPy `scipy.optimize.linprog` and `milp` documentation, <https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html>.

## Promotions and bundles (ideas 5, 7)

17. R. Agrawal, T. Imielinski and A. Swami. Mining association rules between sets of items in large databases. *ACM SIGMOD* 1993.
    Support, confidence and the setting for market-basket analysis; lift is the usual ratio P(A and B) / (P(A) P(B)).
18. S. Brin, R. Motwani, J. D. Ullman and S. Tsur. Dynamic itemset counting and implication rules for market basket data. *ACM SIGMOD* 1997.
    Introduced lift-style interest measures.

## Software

19. pandas, NumPy, SciPy, Matplotlib, pytest: the versions pinned in `requirements.txt` (all open source).
20. Apache Hadoop 3.3.4 (Apache License 2.0). The standalone build in `scripts/setup_hadoop_standalone.sh` uses the official
    `hadoop-client-api` / `hadoop-client-runtime` 3.3.4 jars as shipped inside the PySpark 3.5.1 source package on PyPI, and
    compiles the `hadoop-streaming` source from the `rel/release-3.3.4` tag of <https://github.com/apache/hadoop>. The Apache
    download mirrors and Maven Central were not reachable from the build environment, so these are not the Apache
    binary tarball. SHA-256 of the jars used: hadoop-client-api-3.3.4.jar
    `e513d71b78086b5caaa439f4402b43e20df01446d56b66084ad419452878701c`, hadoop-client-runtime-3.3.4.jar
    `9377a68071137ae5f5c8cdc2ed20d6f904a1df4d06df26b47ed8872a1b0d8d47`; compare with the Apache release checksums.
21. Apache Spark 3.5.1 (Apache License 2.0), used only to execute the HiveQL scripts (`scripts/check_hive_sql.py`).

## Project documents

22. `docs/Hadoop_Demand_Supply_Project_Pack.pdf`: the idea pack this implementation follows (8 ideas, architecture, viva Q&A).
