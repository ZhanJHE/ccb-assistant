# -*- coding: utf-8 -*-
"""下载 AIN 专题 16 篇 arXiv OA PDF 到主题目录，并生成 _raw/convert-meta.json。"""
import os, json, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.dirname(HERE)          # 调研卷宗/智能网络
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

# (编号, arXiv id, 文件名slug, 标题, 出处)
ITEMS = [
 ("AIN-9",  "2609.02140", "SoK-flow-label-provenance", "SoK: Where Do Flow Labels Come From? Auditing Label Provenance in Encrypted Traffic Benchmarks", "arXiv 2026"),
 ("AIN-10", "2608.22683", "Colossus-PQC-ETC", "The Colossus with Feet of Clay: Debunking Encrypted Traffic Classifiers under PQC Evolution", "arXiv 2026"),
 ("AIN-11", "2606.17746", "FlowCLIP", "FlowCLIP: Contrastive Pretraining Using Domain Names for Encrypted Traffic Classification", "arXiv 2026"),
 ("AIN-17", "2609.12263", "Graph-NIDS-first-principles", "A First-Principles Evaluation of Graph-Based Network Intrusion Detection Systems", "arXiv 2026"),
 ("AIN-18", "2609.13511", "LLM-vs-ML-NIDS", "A Three-Axis Stress Test of LLM vs Classical ML for Network Intrusion Detection under Distribution Shift and Adversarial Evasion", "arXiv 2026"),
 ("AIN-19", "2609.16363", "FSNIC-FPGA-SmartNIC-IDS", "FSNIC: A Low-Latency Flow-Based Intrusion Detection Architecture for FPGA SmartNICs", "arXiv 2026"),
 ("AIN-23", "2308.04905", "GraphCC", "GraphCC: A Practical Graph Learning-Based Approach to Congestion Control in Datacenters", "arXiv 2023"),
 ("AIN-26", "2510.25105", "Learning-vs-Human-CC", "Learning-Based vs Human-Derived Congestion Control: An In-Depth Experimental Study", "arXiv 2025"),
 ("AIN-27", "2605.21915", "CCLab", "CCLab: Adversarial Testing of Learning- and Non-Learning-Based Congestion Controllers", "arXiv 2026"),
 ("AIN-33", "2608.22812", "LLM-BGP-security", "The Surprising Effectiveness of LLMs in BGP Security: Mining an Unprecedented Amount of Incidents and Boosting Anomaly Detection", "arXiv 2026"),
 ("AIN-38", "2605.09260", "CoT-mobile-traffic-pred", "Chain-of-Thought Reasoning Enhances In-Context Learning for LLM-Based Mobile Traffic Prediction", "arXiv 2026"),
 ("AIN-39", "2502.12834", "NTP-INT", "NTP-INT: Network Traffic Prediction-Driven In-band Network Telemetry for High-load Switches", "arXiv 2025"),
 ("AIN-40", "2608.23179", "NetConfArena", "NetConfArena: An Executable Benchmark for LLM Agents in Closed-Loop Network Configuration", "arXiv 2026"),
 ("AIN-41", "2512.16381", "Network-Arena-agent-bench", "A Network Arena for Benchmarking AI Agents on Network Troubleshooting", "arXiv 2025"),
 ("AIN-42", "2601.06640", "Agentic-IBN-6G", "Agentic AI Empowered Intent-Based Networking for 6G", "arXiv 2026"),
 ("AIN-43", "2609.12170", "NDT-Factory", "NDT Factory: Synthesizing Verified Network Digital Twins from Semantic Models via Multi-Agent LLM", "arXiv 2026"),
]

os.makedirs(DEST, exist_ok=True)
meta = {}
for num, aid, slug, title, venue in ITEMS:
    fn = f"{num}-{slug}.pdf"
    path = os.path.join(DEST, fn)
    if not os.path.exists(path):
        url = f"https://arxiv.org/pdf/{aid}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
            print(f"OK   {fn} ({len(data)//1024} KB)")
        except Exception as ex:
            print(f"FAIL {fn} <- {url} : {ex}")
            continue
    else:
        print(f"SKIP {fn}（已存在）")
    meta[fn] = {"title": title, "venue": venue, "id": f"arXiv:{aid}", "url": f"https://arxiv.org/abs/{aid}"}
    time.sleep(3)

json.dump(meta, open(os.path.join(HERE, "convert-meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nmeta: {len(meta)} entries -> _raw/convert-meta.json")
