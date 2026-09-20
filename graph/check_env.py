#!/usr/bin/env python3
"""Prove the graph environment works before any real graph code depends on it.

    .venv-graph/bin/python graph/check_env.py

Builds a 4-node graph, then asserts three things GraphFrames must get right for this project: degree counting, motif
matching (the shape of "two modules drawing from one supply"), and connected components. Exit code 1 on any failure.
The first run downloads the GraphFrames JAR from Maven Central (about 2 MB); later runs use the local Ivy cache.
"""
import sys
import tempfile

from graphframes import GraphFrame
from pyspark.sql import SparkSession

# Must match the pinned pyspark major version and graphframes-py in requirements-graph.txt.
GRAPHFRAMES_JAR = "io.graphframes:graphframes-spark4_2.13:0.12.2"


def spark_session(name="gear-graph"):
    """One place that configures Spark, so the real build and this check cannot drift apart."""
    s = (SparkSession.builder.master("local[2]").appName(name)
         .config("spark.jars.packages", GRAPHFRAMES_JAR)
         .config("spark.ui.enabled", "false")
         .config("spark.ui.showConsoleProgress", "false")   # progress bars otherwise overwrite the ok/FAIL lines
         .config("spark.sql.shuffle.partitions", "4")     # the data is tiny; the default 200 only adds overhead
         .getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    s.sparkContext.setCheckpointDir(tempfile.mkdtemp(prefix="gg-ckpt-"))   # connectedComponents needs one
    return s


def main():
    spark = spark_session("gg-check-env")
    v = spark.createDataFrame([("a", "A"), ("b", "B"), ("c", "C"), ("x", "X")], ["id", "name"])
    e = spark.createDataFrame([("b", "a", "SYNCS"), ("a", "c", "AUDIO_TO"), ("b", "c", "AUDIO_TO")], ["src", "dst", "rel"])
    g = GraphFrame(v, e)

    indeg = {r["id"]: r["inDegree"] for r in g.inDegrees.collect()}
    motif = {tuple(r) for r in g.find("(p)-[e1]->(c); (q)-[e2]->(c)").filter("p.id < q.id").select("p.id", "q.id", "c.id").collect()}
    comp = {r["id"]: r["component"] for r in g.connectedComponents().collect()}

    checks = {
        "in-degree": indeg == {"a": 1, "c": 2},
        "motif (two sources, one destination)": motif == {("a", "b", "c")},
        "connected components (a,b,c together; x alone)": comp["a"] == comp["b"] == comp["c"] != comp["x"],
    }
    for name, ok in checks.items():
        print(("ok    " if ok else "FAIL  ") + name)
    spark.stop()
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
