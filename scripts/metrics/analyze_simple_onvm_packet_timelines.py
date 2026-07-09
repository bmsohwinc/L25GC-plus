#!/usr/bin/env python3
from collections import defaultdict
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "exps" / "tslogs" / "merged_20260708_204501.log"
OUT = Path(__file__).resolve().parent / "simple_onvm_packet_timelines"


def read_events():
    component = "onvm_mgr"
    events = []
    with TRACE.open(errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            if "APP: Using Instance ID 1" in line:
                component = "onvm_upf_u"
            elif "APP: Using Instance ID 2" in line:
                component = "onvm_upf_c"
            if not line.startswith("ONVM_PKT_TS,"):
                continue
            _, step, pkt_id, tsc, ns, lcore = line.strip().split(",")
            events.append(
                {
                    "line_no": line_no,
                    "component": component,
                    "step": step,
                    "label": f"{component}.{step}",
                    "pkt_id": pkt_id,
                    "tsc": int(tsc),
                    "ns": int(ns),
                    "lcore": int(lcore),
                }
            )
    return events


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    by_pkt = defaultdict(list)
    labels = []

    for event in read_events():
        by_pkt[event["pkt_id"]].append(event)
        if event["label"] not in labels:
            labels.append(event["label"])

    for pkt_events in by_pkt.values():
        pkt_events.sort(key=lambda e: (e["ns"], e["line_no"]))

    fields = ["pkt_id", "event_count", "first_ns", "last_ns", "span_us", "components", "last_step"]
    for label in labels:
        fields += [f"{label}.ns", f"{label}.since_first_us"]

    with (OUT / "packet_timelines.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for pkt_id, pkt_events in sorted(by_pkt.items(), key=lambda item: item[1][0]["ns"]):
            first_ns = pkt_events[0]["ns"]
            first_by_label = {}
            for event in pkt_events:
                first_by_label.setdefault(event["label"], event)
            row = {
                "pkt_id": pkt_id,
                "event_count": len(pkt_events),
                "first_ns": first_ns,
                "last_ns": pkt_events[-1]["ns"],
                "span_us": f"{(pkt_events[-1]['ns'] - first_ns) / 1000:.3f}",
                "components": "|".join(sorted({e["component"] for e in pkt_events})),
                "last_step": pkt_events[-1]["label"],
            }
            for label in labels:
                event = first_by_label.get(label)
                row[f"{label}.ns"] = event["ns"] if event else ""
                row[f"{label}.since_first_us"] = f"{(event['ns'] - first_ns) / 1000:.3f}" if event else ""
            writer.writerow(row)

    lines = []
    examples = sorted(by_pkt.items(), key=lambda item: (-len(item[1]), item[1][0]["ns"]))[:8]
    for pkt_id, pkt_events in examples:
        first_ns = pkt_events[0]["ns"]
        lines.append(f"packet {pkt_id}: {len(pkt_events)} events, span {(pkt_events[-1]['ns'] - first_ns) / 1000:.3f} us")
        prev_ns = None
        for event in pkt_events:
            since = (event["ns"] - first_ns) / 1000
            delta = "" if prev_ns is None else f"+{(event['ns'] - prev_ns) / 1000:.3f} us"
            lines.append(f"  {since:12.3f} us {delta:>14}  {event['label']}  lcore={event['lcore']}")
            prev_ns = event["ns"]
        lines.append("")
    (OUT / "example_packet_timelines.txt").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
