#!/usr/bin/env bash
# Builds a *standalone* Apache Hadoop 3.3.4 (real MapReduce engine + real Hadoop Streaming, local
# filesystem, one JVM) without needing the Apache download mirrors or Maven Central.
#
# Why this exists: the sandbox this project was developed in can only reach PyPI, GitHub and a few
# other registries.  So the pieces come from:
#   * the official Hadoop 3.3.4 client jars (hadoop-client-api / -runtime), which ship inside the
#     PySpark 3.5.1 source package from PyPI,
#   * the hadoop-streaming source from the apache/hadoop GitHub repository, tag rel/release-3.3.4,
#     compiled here with javac,
#   * commons-cli, commons-logging and slf4j-api from the same PySpark package.
# Nothing is re-implemented: the job runner, sort/shuffle, partitioner, combiner, counters, the
# -files distributed-cache and -cmdenv handling are Hadoop's own classes.
#
# What it is NOT: a cluster.  There is no HDFS NameNode/DataNode and no YARN ResourceManager, so every
# map and reduce task runs inside one JVM (LocalJobRunner) against the local file system.  On a real
# cluster use scripts/run_hadoop.sh with the cluster's own `hadoop` and `hdfs` on PATH.
#
# Usage: scripts/setup_hadoop_standalone.sh [TARGET_DIR=.hadoop]
#   then: export HADOOP_HOME=$PWD/.hadoop PATH=$HADOOP_HOME/bin:$PATH
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-$ROOT/.hadoop}"
PYSPARK_VERSION="${PYSPARK_VERSION:-3.5.1}"      # bundles Hadoop 3.3.4
HADOOP_VERSION="3.3.4"
HADOOP_TAG="rel/release-$HADOOP_VERSION"
WORK="$TARGET/_build"

command -v java >/dev/null  || { echo "java (JDK 8+ with javac) is required" >&2; exit 1; }
command -v javac >/dev/null || { echo "javac is required (install a JDK, not just a JRE)" >&2; exit 1; }
mkdir -p "$TARGET/lib" "$TARGET/bin" "$TARGET/etc/hadoop" "$TARGET/share/hadoop/tools/lib" "$WORK"

echo "[1] Hadoop $HADOOP_VERSION client jars from the PySpark $PYSPARK_VERSION source package (PyPI)"
if [ ! -f "$WORK/pyspark.tar.gz" ]; then
  python3 -m pip download "pyspark==$PYSPARK_VERSION" --no-deps --no-binary :all: -d "$WORK/dl" >/dev/null
  mv "$WORK"/dl/pyspark-*.tar.gz "$WORK/pyspark.tar.gz"
fi
J="pyspark-$PYSPARK_VERSION/deps/jars"
tar -xzf "$WORK/pyspark.tar.gz" --strip-components=3 -C "$TARGET/lib" \
  "$J/hadoop-client-api-$HADOOP_VERSION.jar" "$J/hadoop-client-runtime-$HADOOP_VERSION.jar" \
  "$J/commons-cli-1.5.0.jar" "$J/commons-logging-1.1.3.jar" "$J/slf4j-api-2.0.7.jar" \
  "$J/log4j-api-2.20.0.jar" "$J/log4j-core-2.20.0.jar" "$J/log4j-slf4j2-impl-2.20.0.jar"

echo "[2] hadoop-streaming source, tag $HADOOP_TAG (GitHub, sparse checkout)"
if [ ! -d "$WORK/src" ]; then
  git clone --quiet --depth 1 --branch "$HADOOP_TAG" --filter=blob:none --sparse https://github.com/apache/hadoop "$WORK/src"
  git -C "$WORK/src" sparse-checkout set hadoop-tools/hadoop-streaming
fi

echo "[3] compile hadoop-streaming"
CP="$(ls "$TARGET"/lib/*.jar | tr '\n' ':')"
rm -rf "$WORK/classes" && mkdir -p "$WORK/classes"
# shellcheck disable=SC2046
javac -nowarn -cp "$CP" -d "$WORK/classes" $(find "$WORK/src/hadoop-tools/hadoop-streaming/src/main/java" -name '*.java') 2>&1 \
  | grep -v '^Picked up\|^Note:' || true
jar cfe "$TARGET/share/hadoop/tools/lib/hadoop-streaming-$HADOOP_VERSION.jar" org.apache.hadoop.streaming.HadoopStreaming -C "$WORK/classes" .

echo "[4] config (etc/hadoop) and launchers: bin/hadoop (jar, fs, version), bin/hdfs (dfs)"
cat > "$TARGET/etc/hadoop/core-site.xml" <<'XML'
<?xml version="1.0"?>
<configuration>
  <!-- standalone: local file system instead of HDFS -->
  <property><name>fs.defaultFS</name><value>file:///</value></property>
</configuration>
XML
cat > "$TARGET/etc/hadoop/mapred-site.xml" <<'XML'
<?xml version="1.0"?>
<configuration>
  <!-- standalone: LocalJobRunner (one JVM) instead of YARN -->
  <property><name>mapreduce.framework.name</name><value>local</value></property>
</configuration>
XML
cat > "$TARGET/etc/hadoop/log4j2.properties" <<'XML'
# show Hadoop's own job counters (map/reduce records, spills, combiner) and warnings, nothing else
rootLogger.level = warn
rootLogger.appenderRef.stdout.ref = console
appender.console.type = Console
appender.console.name = console
appender.console.target = SYSTEM_ERR
appender.console.layout.type = PatternLayout
appender.console.layout.pattern = %d{HH:mm:ss} %p %c{1}: %m%n
logger.job.name = org.apache.hadoop.mapreduce.Job
logger.job.level = info
XML
cat > "$TARGET/bin/hadoop" <<'EOF'
#!/usr/bin/env bash
# Minimal launcher for the standalone build: `hadoop jar <jar> [args]` via Hadoop's own RunJar.
HH="$(cd "$(dirname "$0")/.." && pwd)"
CP="$HH/etc/hadoop:$(ls "$HH"/lib/*.jar | tr '\n' ':')"
case "${1:-}" in
  jar)     shift; exec java ${HADOOP_OPTS:-} -cp "$CP" org.apache.hadoop.util.RunJar "$@" ;;
  fs)      shift; exec java ${HADOOP_OPTS:-} -cp "$CP" org.apache.hadoop.fs.FsShell "$@" ;;
  version) exec java ${HADOOP_OPTS:-} -cp "$CP" org.apache.hadoop.util.VersionInfo ;;
  *) echo "standalone launcher supports: jar | fs | version" >&2; exit 2 ;;
esac
EOF
cat > "$TARGET/bin/hdfs" <<'EOF'
#!/usr/bin/env bash
# Minimal launcher for the standalone build: `hdfs dfs ...` via Hadoop's FsShell (local file system).
HH="$(cd "$(dirname "$0")/.." && pwd)"
CP="$HH/etc/hadoop:$(ls "$HH"/lib/*.jar | tr '\n' ':')"
case "${1:-}" in
  dfs) shift; exec java ${HADOOP_OPTS:-} -cp "$CP" org.apache.hadoop.fs.FsShell "$@" ;;
  *) echo "standalone launcher supports: dfs" >&2; exit 2 ;;
esac
EOF
chmod +x "$TARGET/bin/hadoop" "$TARGET/bin/hdfs"

echo "[5] smoke test"
"$TARGET/bin/hadoop" version 2>&1 | grep -E '^Hadoop' | head -1
echo "ok. Now:  export HADOOP_HOME=$TARGET PATH=$TARGET/bin:\$PATH"
