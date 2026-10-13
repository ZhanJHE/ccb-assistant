# -*- coding: utf-8 -*-
"""AIN 最终清单 + Crossref/arXiv 二次核验。
输出 _raw/verified.json 与紧凑清单。"""
import json, os, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "AIN-Research/1.0 (mailto:research@example.com)"

# (编号, 子块, 标题, DOI, arXiv, 引用(S2快照), 一句话结论)
E = [
 ("AIN-1",  "A", "Deep Packet: A Novel Approach for Encrypted Traffic Classification Using Deep Learning", "10.1007/s00500-019-04030-2", "", 1139, "把原始包字节直接喂 1D-CNN 做加密流量分类的奠基工作。"),
 ("AIN-2",  "A", "Deep Learning for Encrypted Traffic Classification: An Overview", "10.1109/MCOM.2019.1800819", "", 553, "早期权威综述，界定 ETC 的问题与深度学习适用面。"),
 ("AIN-3",  "A", "$Deep-Full-Range$: A Deep Learning Based Network Encrypted Traffic Classification and Intrusion Detection Framework", "10.1109/ACCESS.2019.2908225", "", 224, "把加密流量分类与入侵检测放进同一深度学习框架的代表工作。"),
 ("AIN-4",  "A", "DISTILLER: Encrypted Traffic Classification via Multimodal Multitask Deep Learning", "10.1016/j.jnca.2021.102985", "", 189, "多模态多任务（包序+字节图）蒸馏式 ETC。"),
 ("AIN-5",  "A", "A Novel Multimodal Deep Learning Framework for Encrypted Traffic Classification", "10.1109/TNET.2022.3215507", "", 107, "TNET 上的多模态 ETC，代表该子方向系统级设计成熟。"),
 ("AIN-6",  "A", "Deep Learning for Encrypted Traffic Classification in the Face of Data Drift: An Empirical Study", "10.1016/j.comnet.2023.109648", "", 63, "**泼冷水候选**：实证 ETC 模型在数据漂移下显著退化。"),
 ("AIN-7",  "A", "ATVITSC: A Novel Encrypted Traffic Classification Method Based on Deep Learning", "10.1109/TIFS.2024.3433446", "", 69, "面向加密业务的深度学习分类新方法（TIFS'24）。"),
 ("AIN-8",  "A", "Deep Learning and Pre-training Technology for Encrypted Traffic Classification: A Comprehensive Review", "10.1016/j.neucom.2024.128444", "", 59, "预训练范式进入 ETC 的最新综述（最新入口）。"),
 ("AIN-9",  "A", "SoK: Where Do Flow Labels Come From? Auditing Label Provenance in Encrypted Traffic Benchmarks", "", "2609.02140", None, "**泼冷水**：系统审计 ETC 基准的标签来源，质疑评测可信度。"),
 ("AIN-10", "A", "The Colossus with Feet of Clay: Debunking Encrypted Traffic Classifiers under PQC Evolution", "", "2608.22683", None, "**泼冷水**：后量子加密演进下，现有 ETC 分类器被证伪。"),
 ("AIN-11", "A", "FlowCLIP: Contrastive Pretraining Using Domain Names for Encrypted Traffic Classification", "", "2606.17746", None, "用域名做对比预训练，代表 2026 ETC 的预训练主线。"),
 ("AIN-12", "B", "A Deep Learning Approach for Network Intrusion Detection System", "10.4108/eai.3-12-2015.2262516", "", 1288, "NIDS+深度学习奠基文献。"),
 ("AIN-13", "B", "A Deep Learning Approach to Network Intrusion Detection", "10.1109/TETCI.2017.2772792", "", 1571, "自编码器做无监督网络入侵检测的经典高引工作。"),
 ("AIN-14", "B", "Network Intrusion Detection System: A Systematic Study of Machine Learning and Deep Learning Approaches", "10.1002/ett.4150", "", 1160, "ML/DL 做 NIDS 的系统性对比研究。"),
 ("AIN-15", "B", "Machine Learning in Network Anomaly Detection: A Survey", "10.1109/ACCESS.2021.3126834", "", 155, "网络异常检测×ML 的权威综述。"),
 ("AIN-16", "B", "iGuard: Efficient Isolation Forest Design for Malicious Traffic Detection in Programmable Switches", "10.1145/3680121.3697807", "", 7, "CoNEXT'24：数据面内 Isolation Forest 恶意流量检测。"),
 ("AIN-17", "B", "A First-Principles Evaluation of Graph-Based Network Intrusion Detection Systems", "", "2609.12263", None, "**泼冷水**：第一性原理重评图神经网络 NIDS 的真实有效性。"),
 ("AIN-18", "B", "A Three-Axis Stress Test of LLM vs Classical ML for Network Intrusion Detection under Distribution Shift and Adversarial Evasion", "", "2609.13511", None, "LLM vs 经典 ML 做 NIDS 的三轴压力测试。"),
 ("AIN-19", "B", "FSNIC: A Low-Latency Flow-Based Intrusion Detection Architecture for FPGA SmartNICs", "", "2609.16363", None, "FPGA SmartNIC 上的低延迟流级 IDS（与基座/卸载交叉）。"),
 ("AIN-20", "C", "Classic Meets Modern: A Pragmatic Learning-Based Congestion Control for the Internet (PCC-Vivace)", "10.1145/3387514.3405892", "", 318, "学习型 CC 的务实化里程碑。"),
 ("AIN-21", "C", "ACC: Automatic ECN Tuning for High-Speed Datacenter Networks", "10.1145/3452296.3472927", "", 115, "SIGCOMM'21：用学习/自动调参替代手工 ECN 阈值。"),
 ("AIN-22", "C", "Reinforcement Learning for Datacenter Congestion Control", "10.1145/3512798.3512815", "", 50, "把 DRL 用于数据中心拥塞控制的代表工作（含真实训练）。"),
 ("AIN-23", "C", "GraphCC: A Practical Graph Learning-Based Approach to Congestion Control in Datacenters", "", "2308.04905", 9, "图学习做数据中心 CC，把拓扑/流关系纳入决策。"),
 ("AIN-24", "C", "Achieving Fairness Generalizability for Learning-Based Congestion Control with Jury", "10.1145/3689031.3696065", "", 13, "EuroSys'25：面向公平性泛化的学习型 CC。"),
 ("AIN-25", "C", "EchoCC: Refining Learning-Based Congestion Control with WordBook", "10.1109/TON.2025.3566495", "", 2, "ToN'25：用码本/记忆精化学习型 CC。"),
 ("AIN-26", "C", "Learning-Based vs Human-Derived Congestion Control: An In-Depth Experimental Study", "", "2510.25105", 3, "**泼冷水**：实证揭示学习型 CC 的根本局限，仍难上生产。"),
 ("AIN-27", "C", "CCLab: Adversarial Testing of Learning- and Non-Learning-Based Congestion Controllers", "", "2605.21915", None, "对学习/非学习 CC 的统一对抗测试框架。"),
 ("AIN-28", "D", "Spatial-Temporal Large Language Model for Traffic Prediction", "10.1109/MDM61037.2024.00025", "", 233, "把 LLM 引入时空流量预测的高引工作。"),
 ("AIN-29", "D", "Towards Intent-Based Network Management: Large Language Models for Intent Extraction in 5G Core Networks", "10.1109/DRCN60692.2024.10539172", "", 79, "LLM 做意图抽取，IBN 的早期代表。"),
 ("AIN-30", "D", "Intent-Based Network Configuration Using Large Language Models", "10.1002/nem.2313", "", 35, "LLM 驱动意图式网络配置。"),
 ("AIN-31", "D", "LLNet: An Intent-Driven Approach to Instructing Softwarized Network Devices Using a Small Language Model", "10.1109/TNSM.2025.3570017", "", 31, "小语言模型做意图式设备指令（TNSM'25）。"),
 ("AIN-32", "D", "A Survey of Anomaly Detection and Root Cause Analysis Techniques for AIOps in Large-Scale Software Systems", "10.1109/AIITA69518.2026.11567316", "", 0, "AIOps 异常检测+RCA 的最新综述（近年入口）。"),
 ("AIN-33", "D", "The Surprising Effectiveness of LLMs in BGP Security: Mining an Unprecedented Amount of Incidents and Boosting Anomaly Detection", "", "2608.22812", None, "LLM 用于 BGP 安全：挖掘事故并提升异常检测。"),
 ("AIN-34", "E", "Unveiling the Potential of Graph Neural Networks for Network Modeling and Optimization in SDN", "10.1145/3314148.3314357", "", 224, "GNN 做网络建模/优化的奠基。"),
 ("AIN-35", "E", "Graph Neural Networks for Communication Networks: Context, Use Cases and Opportunities", "10.1109/MNET.123.2100773", "", 115, "GNN×通信网络的应用综述。"),
 ("AIN-36", "E", "RouteNet-Fermi: Network Modeling with Graph Neural Networks", "10.1109/TNET.2023.3269983", "", 110, "GNN 网络性能建模的代表系统（RouteNet 线）。"),
 ("AIN-37", "E", "Network Digital Twin: Context, Enabling Technologies, and Opportunities", "10.1109/MCOM.001.2200012", "", 181, "网络数字孪生的定位性综述（与 WTP 数字孪生条目呼应）。"),
]

def crossref(doi):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi) + "?mailto=research@example.com"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        m = json.loads(r.read().decode("utf-8", "replace"))["message"]
    ct = (m.get("container-title") or [None])[0]
    yr = (m.get("issued", {}).get("date-parts") or [[None]])[0][0]
    return ct, yr, m.get("type"), (m.get("title") or [None])[0]

def arxiv_meta(aid):
    url = "http://export.arxiv.org/api/query?id_list=" + aid + "&max_results=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        root = ET.fromstring(r.read().decode("utf-8", "replace"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    e = root.find("a:entry", ns)
    if e is None:
        return None, None
    return " ".join(e.find("a:title", ns).text.split()), e.find("a:published", ns).text[:10]

out = []
for num, sub, title, doi, ax, cite, note in E:
    ven = yr = None; typ = None
    try:
        if doi:
            ven, yr, typ, _ = crossref(doi)
        elif ax:
            t2, d2 = arxiv_meta(ax)
            ven, yr = "arXiv preprint", (d2[:4] if d2 else None)
    except Exception as ex:
        ven = f"ERR:{ex}"
    out.append(dict(num=num, sub=sub, title=title, doi=doi, arxiv=ax, citations=cite, venue=ven, year=yr, note=note))
    print(f"{num} [{sub}] {yr} | {ven} | {title}")
    time.sleep(1)

json.dump(out, open(os.path.join(HERE, "raw", "verified.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n{len(out)} entries written to raw/verified.json")
