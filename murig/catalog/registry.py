# -*- coding: utf-8 -*-
"""内置组件清单（build_components）、抓取函数注册表与调度线程。"""

from __future__ import annotations

from functools import partial
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from ..core.constants import CURRENT_OS, IS_ARM
from ..core.models import Component, ComponentVersion
from .cache import cached_versions
from .fetch import *  # noqa: F401,F403  版本抓取函数
from .urls import *  # noqa: F401,F403  URL 构造函数


_RAW_FETCHERS: Dict[str, Callable[[], List[ComponentVersion]]] = {
    "jdk": fetch_jdk_versions,
    "maven": fetch_maven_versions,
    "tomcat": fetch_tomcat_versions,
    "python": fetch_python_versions,
    "node": fetch_node_versions,
    "mysql": fetch_mysql_versions,
    "git": fetch_git_versions,
    "conda": fetch_conda_versions,
    "redis": fetch_redis_versions,
    "elasticsearch": fetch_es_versions,
    "ollama": fetch_ollama_versions,
    "hadoop": fetch_hadoop_versions,
    "zookeeper": fetch_zookeeper_versions,
    "hive": fetch_hive_versions,
    "hbase": fetch_hbase_versions,
    "spark": fetch_spark_versions,
    "flink": fetch_flink_versions,
    "kafka": fetch_kafka_versions,
    "claude-code": fetch_claude_code_versions,
    "cc-switch": fetch_ccswitch_versions,
    "postgresql": fetch_pg_versions,
    "opengauss": fetch_opengauss_versions,
    "dameng": fetch_dameng_versions,
    "oceanbase": fetch_oceanbase_versions,
    "kingbase": fetch_kingbase_versions,
    "yashandb": fetch_yashandb_versions,
}

# 统一套一层本地缓存：抓取失败（限流/断网/代理拦截）时回退最近一次成功结果
FETCHERS: Dict[str, Callable[[], List[ComponentVersion]]] = {
    key: partial(cached_versions, key, fn) for key, fn in _RAW_FETCHERS.items()
}


class VersionFetchWorker(QThread):
    """在后台线程里跑抓取器，避免阻塞 UI。"""

    done = Signal(str, object)  # (component_key, versions or None)

    def __init__(self, key: str, fetcher: Callable[[], List[ComponentVersion]],
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.key = key
        self.fetcher = fetcher

    def run(self) -> None:  # noqa: D401
        try:
            vs = self.fetcher()
            self.done.emit(self.key, vs)
        except Exception as exc:  # pragma: no cover
            print(f"[fetch:{self.key}] {exc}")
            self.done.emit(self.key, None)


def build_components() -> List[Component]:
    """构造预置的组件与版本信息（作为抓取完成前的默认列表）。"""

    components: List[Component] = []

    # ------------------ JDK ------------------
    components.append(
        Component(
            key="jdk",
            display_name="JDK (Temurin)",
            env_var="JAVA_HOME",
            path_subdir="bin",
            exec_name="java",
            version_args=["-version"],
            versions=[
                ComponentVersion(
                    version=v,
                    url_map=_adoptium_jdk_url(v),
                    archive_map={"Windows": "zip", "Darwin": "tar.gz", "Linux": "tar.gz"},
                )
                for v in ("21", "17", "11", "8")
            ],
            category="java",
            aliases=["java", "temurin", "jre"],
        )
    )

    # ------------------ Maven ------------------
    components.append(
        Component(
            key="maven",
            display_name="Apache Maven",
            env_var="MAVEN_HOME",
            path_subdir="bin",
            exec_name="mvn",
            version_args=["-v"],
            versions=[_cv(v, _maven_urls(v)) for v in ("3.9.6", "3.9.5", "3.8.8", "3.6.3")],
            category="java",
        )
    )

    # ------------------ Tomcat ------------------
    components.append(
        Component(
            key="tomcat",
            display_name="Apache Tomcat",
            env_var="CATALINA_HOME",
            path_subdir="bin",
            exec_name="catalina",
            version_args=["version"],
            versions=[_cv(v, _tomcat_urls(v)) for v in ("10.1.24", "9.0.89", "8.5.100")],
            category="java",
        )
    )

    # ------------------ MySQL ------------------
    components.append(
        Component(
            key="mysql",
            display_name="MySQL Server",
            env_var="MYSQL_HOME",
            path_subdir="bin",
            exec_name="mysql",
            version_args=["--version"],
            # macOS ARM64 无 5.7 构建，默认列表里不放死链
            versions=[_cv(v, _mysql_urls(v)) for v in (
                ("9.7.1", "8.4.10", "8.0.45", "8.0.37")
                if CURRENT_OS == "Darwin" and IS_ARM
                else ("9.7.1", "8.4.10", "8.0.45", "8.0.37", "5.7.44")
            )],
            category="database",
            well_known_homes=[
                # macOS 官方 pkg（/usr/local/mysql 是版本目录的符号链接）
                "/usr/local/mysql",
                "/opt/homebrew/opt/mysql",
                "/usr/local/opt/mysql",
                # Windows MySQL Installer / MSI
                "C:/Program Files/MySQL/MySQL Server *",
                "C:/Program Files (x86)/MySQL/MySQL Server *",
            ],
        )
    )

    # ------------------ Python ------------------
    components.append(
        Component(
            key="python",
            display_name="Python",
            env_var=None,
            path_subdir="Scripts" if CURRENT_OS == "Windows" else "bin",
            exec_name="python3" if CURRENT_OS != "Windows" else "python",
            version_args=["--version"],
            versions=[_cv(v, _python_urls(v)) for v in ("3.12.4", "3.11.9", "3.10.14", "3.9.19")],
            category="python",
        )
    )

    # ------------------ Node.js ------------------
    components.append(
        Component(
            key="node",
            display_name="Node.js",
            env_var="NODE_HOME",
            path_subdir="bin",
            exec_name="node",
            version_args=["--version"],
            versions=[_cv(v, _node_urls(v)) for v in ("20.15.0", "18.20.3", "16.20.2")],
            category="frontend",
            aliases=["node", "npm"],
        )
    )

    # ------------------ Git ------------------
    # macOS/Linux 一般依赖系统自带 git；Windows 用 MinGit 便携版
    components.append(
        Component(
            key="git",
            display_name="Git",
            env_var=None,
            path_subdir="cmd" if CURRENT_OS == "Windows" else "bin",
            exec_name="git",
            version_args=["--version"],
            versions=[_cv(v, _git_urls(v)) for v in ("2.45.2", "2.44.0", "2.43.0")],
            category="frontend",
        )
    )

    # ------------------ Miniconda ------------------
    # 安装器模式：exe/sh 静默安装到 install_dir
    conda_versions = []
    for v in ("py312_24.7.1-0", "py311_24.7.1-0", "py310_24.5.0-0"):
        cv = ComponentVersion(
            version=v,
            url_map=_conda_urls(v),
            archive_map={"Windows": "exe", "Darwin": "sh", "Linux": "sh"},
        )
        conda_versions.append(cv)
    components.append(
        Component(
            key="conda",
            display_name="Miniconda",
            env_var="CONDA_HOME",
            path_subdir="Scripts" if CURRENT_OS == "Windows" else "bin",
            exec_name="conda",
            version_args=["--version"],
            versions=conda_versions,
            installer_mode=True,
            installer_args={
                # /S = silent, /D=path 必须放最后
                "Windows": ["/S", "/InstallationType=JustMe", "/RegisterPython=0", "/AddToPath=0"],
                # -b batch, -f force overwrite, -p prefix
                "Darwin": ["-b", "-f", "-p"],
                "Linux": ["-b", "-f", "-p"],
            },
            category="python",
        )
    )

    # ------------------ Redis ------------------
    # Windows 走 redis-windows 移植版 zip；macOS/Linux 为官方源码包，解压后自动 make 编译
    components.append(
        Component(
            key="redis",
            display_name="Redis",
            env_var="REDIS_HOME",
            path_subdir="bin",
            exec_name="redis-server",
            version_args=["--version"],
            versions=[_cv(v, _redis_urls(v)) for v in ("8.4.7", "7.4.11", "7.2.16", "6.2.24")],
            category="database",
            aliases=["缓存", "cache"],
            # 源码包需要编译；产物在 src/ 目录
            after_extract=[["make", "-j4"]] if CURRENT_OS != "Windows" else None,
            extra_bin_dirs=["src"] if CURRENT_OS != "Windows" else [],
        )
    )

    # ------------------ Elasticsearch ------------------
    components.append(
        Component(
            key="elasticsearch",
            display_name="Elasticsearch",
            env_var="ES_HOME",
            path_subdir="bin",
            exec_name="elasticsearch",
            version_args=["--version"],
            versions=[_cv(v, _es_urls(v)) for v in ("8.15.2", "7.17.24")],
            category="database",
            aliases=["es", "搜索引擎"],
        )
    )

    # ------------------ Ollama ------------------
    # Linux tgz 解压为 usr/bin/ollama；macOS zip 为 Ollama.app；Windows zip 解压即用
    components.append(
        Component(
            key="ollama",
            display_name="Ollama",
            env_var=None,
            # Linux/Windows：bin/ollama；macOS：Ollama.app/Contents/Resources/ollama
            path_subdir="bin",
            exec_name="ollama",
            version_args=["--version"],
            versions=[_tgz_cv(v, _ollama_urls(v)) for v in ("0.12.9", "0.3.14")],
            category="ai",
            aliases=["大模型", "llm", "本地模型"],
            extra_bin_dirs=["Contents/Resources", "Contents/MacOS"],
        )
    )

    # ------------------ Hadoop ------------------
    components.append(
        Component(
            key="hadoop",
            display_name="Apache Hadoop",
            env_var="HADOOP_HOME",
            path_subdir="bin",
            exec_name="hadoop",
            version_args=["version"],
            versions=[_tgz_cv(v, _hadoop_urls(v)) for v in ("3.5.0", "3.4.3", "3.3.6")],
            category="bigdata",
            aliases=["hdfs", "mapreduce"],
        )
    )

    # ------------------ ZooKeeper ------------------
    components.append(
        Component(
            key="zookeeper",
            display_name="Apache ZooKeeper",
            env_var="ZOOKEEPER_HOME",
            path_subdir="bin",
            exec_name="zkServer",
            version_args=["version"],
            versions=[_tgz_cv(v, _zookeeper_urls(v)) for v in ("3.9.6", "3.8.4")],
            category="bigdata",
            aliases=["zk"],
        )
    )

    # ------------------ Hive ------------------
    components.append(
        Component(
            key="hive",
            display_name="Apache Hive",
            env_var="HIVE_HOME",
            path_subdir="bin",
            # 用 beeline --version 探测（hive CLI 对 --version 的支持不稳定）
            exec_name="beeline",
            version_args=["--version"],
            versions=[_tgz_cv(v, _hive_urls(v)) for v in ("4.2.1", "4.0.1", "3.1.3")],
            category="bigdata",
        )
    )

    # ------------------ HBase ------------------
    components.append(
        Component(
            key="hbase",
            display_name="Apache HBase",
            env_var="HBASE_HOME",
            path_subdir="bin",
            exec_name="hbase",
            version_args=["version"],
            versions=[_tgz_cv(v, _hbase_urls(v)) for v in ("3.0.0", "2.6.7", "2.6.0")],
            category="bigdata",
        )
    )

    # ------------------ Spark ------------------
    components.append(
        Component(
            key="spark",
            display_name="Apache Spark",
            env_var="SPARK_HOME",
            path_subdir="bin",
            exec_name="spark-submit",
            version_args=["--version"],
            versions=[_tgz_cv(v, _spark_urls(v)) for v in ("4.2.0", "4.0.0", "3.5.3")],
            category="bigdata",
        )
    )

    # ------------------ Flink ------------------
    components.append(
        Component(
            key="flink",
            display_name="Apache Flink",
            env_var="FLINK_HOME",
            path_subdir="bin",
            exec_name="flink",
            version_args=["--version"],
            versions=[_tgz_cv(v, _flink_urls(v)) for v in ("2.3.0", "1.20.0", "1.18.1")],
            category="bigdata",
        )
    )

    # ------------------ Kafka ------------------
    components.append(
        Component(
            key="kafka",
            display_name="Apache Kafka",
            env_var="KAFKA_HOME",
            path_subdir="bin",
            exec_name="kafka-topics",
            version_args=["--version"],
            versions=[_tgz_cv(v, _kafka_urls(v)) for v in ("4.3.1", "3.9.0", "3.8.1")],
            category="bigdata",
        )
    )

    # ------------------ Claude Code（AI） ------------------
    # 通过本机 npm 便携安装到独立目录（前置：已安装 Node.js）
    components.append(
        Component(
            key="claude-code",
            display_name="Claude Code",
            env_var="CLAUDE_CODE_HOME",
            path_subdir="node_modules/.bin",
            exec_name="claude",
            version_args=["--version"],
            versions=[
                ComponentVersion(v, {"Windows": "npm", "Darwin": "npm", "Linux": "npm"})
                for v in ("2.1.292", "2.1.291", "2.1.290")
            ],
            category="ai",
            aliases=["claude", "cc", "anthropic"],
            npm_package="@anthropic-ai/claude-code",
            extra_bin_dirs=["node_modules/.bin"],
        )
    )

    # ------------------ CC-Switch（AI） ------------------
    # Windows 便携 zip（cc-switch.exe）/ macOS「CC Switch.app」/ Linux AppImage
    components.append(
        Component(
            key="cc-switch",
            display_name="CC-Switch",
            env_var=None,
            path_subdir="",  # Linux AppImage 重命名后放在安装目录根
            exec_name="cc-switch",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    v,
                    _ccswitch_urls(v),
                    {"Windows": "zip", "Darwin": "tar.gz", "Linux": "bin"},
                )
                for v in ("4.0.4", "4.0.3", "4.0.2")
            ],
            category="ai",
            aliases=["ccswitch", "cc switch", "供应商切换", "镜像源切换"],
            extra_bin_dirs=["CC Switch.app/Contents/MacOS", ""],
            raw_bin_name="cc-switch",
            # 桌面 GUI 应用：探测版本时执行 cc-switch.exe 会直接打开程序窗口
            gui_app=True,
        )
    )

    # ------------------ PostgreSQL（数据库） ------------------
    # Win/macOS 用 EDB 免安装 zip；Linux 用官方源码自动编译（不依赖 readline/zlib）
    pg_after_extract = None
    if CURRENT_OS == "Linux":
        pg_after_extract = [
            ["./configure", "--prefix={home}", "--without-readline", "--without-zlib"],
            ["make", "-j4"],
            ["make", "install"],
        ]
    components.append(
        Component(
            key="postgresql",
            display_name="PostgreSQL",
            env_var="PG_HOME",
            path_subdir="bin",
            exec_name="psql",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    v,
                    _pg_urls(v),
                    {"Windows": "zip", "Darwin": "zip", "Linux": "tar.gz"},
                )
                for v in ("18.4", "17.9", "16.13")
            ],
            category="database",
            aliases=["pg", "postgres", "postgre"],
            # Linux 源码 make install 后 bin 在根下；Win/macOS EDB 包带一层 pgsql/ 根目录
            extra_bin_dirs=["pgsql/bin"],
            after_extract=pg_after_extract,
            post_notes=[
                "本工具只完成下载/编译与环境变量配置；初始化数据库请执行 initdb -D <数据目录>，再用 pg_ctl 启动。",
            ] if CURRENT_OS == "Linux" else [
                "本工具只完成下载与环境变量配置；初始化数据库请执行 initdb -D <数据目录>，再用 pg_ctl 启动。",
            ],
        )
    )

    # ------------------ openGauss（信创数据库，仅 Linux） ------------------
    # Lite 外层是 install.sh + .bin 载荷；after_extract 把 .bin（标准 bin/lib 布局）解到安装目录
    components.append(
        Component(
            key="opengauss",
            display_name="openGauss",
            env_var="OPENGAUSS_HOME",
            path_subdir="bin",
            exec_name="gsql",
            version_args=["--version"],
            versions=[_tgz_cv(v, _opengauss_urls(v)) for v in ("7.0.0", "6.0.1", "6.0.0")],
            category="database",
            aliases=["高斯", "华为数据库", "gaussdb", "信创"],
            after_extract=[
                ["sh", "-c", "tar -zxf openGauss-Lite-*.bin && rm -f openGauss-Lite-*.bin"]
            ],
            post_notes=[
                "解压解包的是程序本体（bin/gsql 等）；如需初始化单机实例，可在安装目录外层使用官方 install.sh -R <程序目录> -D <数据目录>。",
            ],
        )
    )

    # ------------------ 达梦 DM8（信创数据库） ------------------
    # 官方分发包是 zip 套 ISO；本工具完成下载+解出 ISO，安装需挂载后运行镜像内安装器
    dm_label = "2026.07.09" if CURRENT_OS == "Windows" else "2026.07.10"
    components.append(
        Component(
            key="dameng",
            display_name="达梦数据库 DM8",
            env_var=None,
            path_subdir="",
            exec_name=None,
            versions=[
                ComponentVersion(
                    dm_label,
                    _dameng_default_urls(),
                    {"Windows": "zip", "Linux": "zip"},
                )
            ],
            category="database",
            aliases=["达梦", "dm", "dameng", "信创"],
            post_notes=[
                "解压后得到的是 ISO 镜像：Windows 请双击挂载后运行安装程序；Linux 请 mount -o loop <ISO> 后执行 ./DMInstall.bin -i。",
                "如需静默安装，可参考达梦官方文档使用 auto_install.xml。",
            ],
        )
    )

    # ------------------ OceanBase（信创数据库，仅 Linux） ------------------
    ob_default_versions = [
        (
            "4.4.2.3",
            "v4.4.2_CE_BP3",
            "oceanbase-ce-4.4.2.3-103000052026090811.el7.x86_64.rpm",
        ),
        (
            "4.3.5.6",
            "v4.3.5_CE_BP6",
            "oceanbase-ce-4.3.5.6-106000012026040916.el7.x86_64.rpm",
        ),
    ]
    ob_versions: List[ComponentVersion] = []
    for v, tag, rpm_name in ob_default_versions:
        url = f"https://github.com/oceanbase/oceanbase/releases/download/{tag}/{rpm_name}"
        ob_versions.append(ComponentVersion(
            version=v,
            url_map={"Windows": "", "Darwin": "", "Linux": url},
            archive_map={"Linux": "rpm"},
        ))
    components.append(
        Component(
            key="oceanbase",
            display_name="OceanBase",
            env_var="OB_HOME",
            path_subdir="bin",
            exec_name="observer",
            version_args=["-V"],
            versions=ob_versions,
            category="database",
            aliases=["ob", "蚂蚁数据库", "信创"],
            extra_bin_dirs=["home/admin/oceanbase/bin", "home/admin/oceanbase/lib"],
            post_notes=[
                "RPM 已便携解包到 home/admin/oceanbase；observer 启动需配置文件与数据目录，请参照 OceanBase 官方文档。",
            ],
        )
    )

    # ------------------ MariaDB（MySQL 社区分支） ------------------
    components.append(
        Component(
            key="mariadb",
            display_name="MariaDB",
            env_var="MARIADB_HOME",
            path_subdir="bin",
            exec_name="mariadb",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    v,
                    _mariadb_urls(v),
                    {"Windows": "zip", "Linux": "tar.gz"},
                )
                for v in ("12.3.3", "11.4.13", "10.11.13")
            ],
            category="database",
            aliases=["maria", "mariadb", "mysql分支", "mysql 分支"],
            post_notes=[
                "首次使用请初始化数据目录：scripts/mariadb-install-db --datadir=<数据目录>，"
                "再用 bin/mariadbd-safe 启动（生产环境建议使用包内 systemd 单元）。",
            ] if CURRENT_OS == "Linux" else [
                "首次使用请以管理员身份运行 bin\\mariadb-install-db.exe 初始化数据目录；"
                "启动可执行 bin\\mariadbd.exe，或注册服务：mariadbd.exe --install。",
            ],
        )
    )

    # ------------------ SQL Server 2025 Express（仅 Windows 引导） ------------------
    # 微软只提供在线引导程序（fwlink，约 4.5MB），无便携包；本工具下载 exe 后请按向导安装
    components.append(
        Component(
            key="sqlserver",
            display_name="SQL Server 2025 Express",
            env_var=None,
            path_subdir="",
            exec_name=None,
            versions=[
                ComponentVersion(
                    "2025 Express",
                    {
                        "Windows": "https://go.microsoft.com/fwlink/p/?linkid=2216019&clcid=0x409",
                        "Darwin": "",
                        "Linux": "",
                    },
                    {"Windows": "exe"},
                )
            ],
            category="database",
            aliases=["mssql", "sqlserver", "sql server", "微软数据库"],
            raw_bin_name="SQL2025-SSEI-Expr.exe",
            post_notes=[
                "下载的是在线引导程序 SQL2025-SSEI-Expr.exe：请双击运行，按向导选择安装类型"
                "（基本 / 自定义 / 仅下载介质），安装包本体在引导过程中在线拉取。",
                "Linux 与 macOS 请使用 Docker 镜像 mcr.microsoft.com/mssql/server 运行。",
            ],
        )
    )

    # ------------------ TiDB（分布式数据库，仅 Linux） ------------------
    # tiup-mirrors 直链；tar 内仅一个 tidb-server，学习可用内嵌 unistore 单机启动
    tidb_arch = "arm64" if IS_ARM else "amd64"
    components.append(
        Component(
            key="tidb",
            display_name="TiDB",
            env_var="TIDB_HOME",
            path_subdir="",
            exec_name="tidb-server",
            version_args=["-V"],
            versions=[
                ComponentVersion(
                    v,
                    {"Windows": "", "Darwin": "",
                     "Linux": f"https://tiup-mirrors.pingcap.com/tidb-v{v}-linux-{tidb_arch}.tar.gz"},
                    {"Linux": "tar.gz"},
                )
                for v in ("8.5.6", "8.1.2", "7.5.7")
            ],
            category="database",
            aliases=["tidb", "pingcap", "分布式数据库"],
            post_notes=[
                "包内仅 tidb-server 一个可执行文件：学习测试可执行 "
                "tidb-server -P 4000 --store=unistore --path=<数据目录> 启动内嵌存储单机实例。",
                "生产集群还需 PD、TiKV 等组件（tiup-mirrors 上同名 pd-/tikv- 包），"
                "建议按官方文档使用 tiup 部署。",
            ],
        )
    )

    # ------------------ 人大金仓 KingbaseES（仅 Linux 便携包） ------------------
    # 主流 V9R1C10 是需申请的 GUI ISO；官网另发布免登录 kingbase-server 便携 tar（金融版构建，
    # 自带 license.dat）。OSS Referer 防盗链：组件声明 download_headers 下载时自动带 Referer。
    kb_oss = "https://kingbase.oss-cn-beijing.aliyuncs.com/upload/KESV9-baseline/Medition/waihuijyzx"
    kb_default = [
        (
            "V009R003C011B0003PS008",
            "V9R3C11 PS008",
            f"{kb_oss}/V9R3C11/V009R003C011B0003PS008/"
            "kingbase-server-V009R003C011B0003PS008-linux-x86_64.tar",
        ),
        (
            "V008R006C008B0015PS008",
            "V8R6C8 PS008",
            f"{kb_oss}/V8R6C8B15/V008R006C008B0015PS008/"
            "kingbase-server-V008R006C008B0015PS008-linux-x86_64.tar",
        ),
    ]
    components.append(
        Component(
            key="kingbase",
            display_name="人大金仓 KingbaseES",
            env_var="KINGBASE_HOME",
            path_subdir="bin",
            exec_name="ksql",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    build,
                    {"Windows": "", "Darwin": "", "Linux": url},
                    {"Linux": "tar"},
                    display_label=label,
                )
                for build, label, url in kb_default
            ],
            category="database",
            aliases=["金仓", "kingbase", "kingbasees", "kes", "信创"],
            download_headers={"Referer": "https://www.kingbase.com.cn/"},
            post_notes=[
                "tar 解包为标准 bin/lib 布局（bin/ 下自带 license.dat）；初始化："
                "bin/initdb -D <数据目录> -U system，再 bin/sys_ctl start -D <数据目录> 启动。",
                "Windows 需使用官网 GUI 安装 ISO（kingbase.com.cn，需申请）。",
            ],
        )
    )

    # ------------------ 崖山 YashanDB（仅 Linux） ------------------
    # 外层 tar：bin/yasboot + depends/ + install.sh + 内层 database-*.tar.gz
    yas_default = "23.4.1.109"
    components.append(
        Component(
            key="yashandb",
            display_name="崖山数据库 YashanDB",
            env_var="YASHANDB_HOME",
            path_subdir="bin",
            exec_name="yasql",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    yas_default,
                    {"Windows": "", "Darwin": "",
                     "Linux": "https://yashandb-website.oss-cn-shenzhen.aliyuncs.com/"
                              "2026/03/06/1772763539649-g3Hyashandb-23.4.1.109-linux-x86_64%20(2).tar.gz"},
                    {"Linux": "tar.gz"},
                )
            ],
            category="database",
            aliases=["崖山", "yashan", "yashandb", "信创"],
            after_extract=[
                ["sh", "-c", "tar -zxf database-*.tar.gz && rm -f database-*.tar.gz"]
            ],
            post_notes=[
                "初始化：在安装目录执行 ./install.sh（等价 yasboot init，交互输入数据目录与口令；"
                "要求 /proc/sys/kernel/pid_max ≥ 32769）。",
                "启动：bin/yasboot cluster start -d <数据目录>；连接："
                "bin/yasql sys/<口令>@127.0.0.1:1688。",
            ],
        )
    )

    return components
