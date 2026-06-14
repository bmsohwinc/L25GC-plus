# `test_nrdc_local.sh` — single-host NR-DC end-to-end test

This script brings up a **complete NR Dual Connectivity (NR-DC)** scenario on a
single machine and asserts that the new **session-local DL FAR** code path in
UPF-U is actually exercised by live traffic.

It exists to answer one question: *does a downlink packet for a dual-connected UE
get hash-steered onto the secondary (SN) GTP tunnel by the new per-session
forwarding logic?* The script proves this by grepping UPF-U/UPF-C logs for the
canonical log strings the new code emits.

---

## 1. What "PASS" means

The new code emits four log strings. The script counts them and decides PASS/FAIL:

| Log string (grep target)        | Emitted by | Meaning |
|---------------------------------|------------|---------|
| `DL path upsert: session=…`     | UPF-C      | A FAR was registered into the session's `dl_paths` set (one per master + DC tunnel). |
| `DL path select: session=…`     | UPF-U      | A real DL packet was hash-steered to one of the installed paths. |
| `DL path remove: session=…`     | UPF-C      | A FAR was withdrawn from `dl_paths`. |
| `DC final path: …`              | UPF-U      | The path chosen for a DL packet after DC selection. |

**PASS** requires: `upserts ≥ 2` **and** `selects ≥ 1` **and** `finals ≥ 1`.

- `≥2 upserts` → both the master and the DC FAR were installed (`dl_paths.count`
  reached 2), so there is something to load-balance across.
- `≥1 select` → UPF-U's `packet_handler` actually picked a DC tunnel for at least
  one downlink packet.

A typical passing run reports something like
`DL path upsert: 3, select: 20, remove: 1, DC final path: 20`.

There is also a **PARTIAL** state (upserts but no selects) and a **FAIL** state
(no `DL path` lines at all); both print targeted hints about what to check.

---

## 2. Topology

All on one host, wired through network namespaces created by
`free-ran-ue/script/namespace-script/free-ran-ue-dc-namespace.sh`:

```
  host  brHost   10.0.1.1            AMF NGAP (N2) listen, UPF-C/U N3 endpoint
  ns    mran-ns  10.0.1.2 / 10.0.2.1  master gNB    (api :40104, xn :31415)
  ns    sran-ns  10.0.1.3 / 10.0.3.1  secondary gNB (api :40104, xn :31415)
  ns    ue-ns    10.0.2.2 / 10.0.3.2  UE
  ns    dn-ns    10.200.0.2           local data network (when CORE_IFACE=brDN)
```

The dataplane uses ONVM with the **AF_PACKET** local backend (no physical NIC
needed) — `ONVM_AF_PACKET_ACCESS_IFACE=brHost`, `ONVM_AF_PACKET_CORE_IFACE=brDN`.

---

## 3. Execution flow

The script runs these stages in order; each has a readiness gate and fails fast
with a log tail if its gate is not met.

1. **Preflight** — verify all binaries exist (amf/smf/nrf, UPF-C/U, the NR-DC
   selftest, Go 1.25.5, and the `free-ran-ue` RAN simulator). If the RAN
   simulator is missing, it falls back to a **logic-only selftest**
   (`l25gc_nrdc_selftest`) that exercises the same session-local code without a
   live RAN, and the script exits on that result.
2. **Clean** — `stop_cn.sh`, kill leftover `free-ran-ue`, clear logs, tear down
   any stale local DN topology.
3. **Namespaces** — (re)create the DC namespaces.
4. **Local DN namespace** — when `CORE_IFACE=brDN`, build a `dn-ns` so downlink
   traffic has a source on the core side.
5. **Config staging** — back up `amfcfg/smfcfg/upfcfg/upf_u` and rewrite them for
   single-host: AMF `ngapIpList` → `10.0.1.1` (drops the second entry), SMF/UPF
   N3 → `10.0.1.1`, and UPF-U MACs/IPs (`an_mac`, `dc_an_mac`, `dc_gnb_ip=10.0.1.3`,
   `upf_ip=10.0.1.1`, `dn_mac`). **Originals are restored on exit** via an
   `EXIT` trap, so your tree is left clean.
6. **Mongo / subscriber** — ensure `mongod` is up and subscriber
   `imsi-208930000000001` is provisioned (inserts it if missing).
7. **ONVM manager** — launch the manager for the AF_PACKET dataplane.
8. **UPF-C + UPF-U** — launch both as ONVM secondaries; wait for
   `Set log level: info` (UPF-C) and `Flow table configured.` (UPF-U).
9. **Control-plane NFs (staged)** — this is the flaky part that the script
   carefully sequences:
   - **NRF** first, wait for `SBI server started`.
   - **AMF** with a **stability retry** (`AMF_MAX_ATTEMPTS=3`): launch, wait for
     the N2 SCTP socket on `10.0.1.1:38412` *with the process alive*, then
     require liveness to hold a further 5 s. This catches the known
     "AMF prints its banner then crashes" race; on a crash it kills and retries.
   - **Remaining NFs** (smf, udr, pcf, udm, nssf, ausf, chf) **one-by-one**,
     re-checking AMF health after each so a late death is attributed correctly.
10. **PFCP** — wait for SMF↔UPF association (`UPF(127.0.0.8) setup association`).
11. **RAN** — launch master gNB (mran-ns) and secondary gNB (sran-ns), each with
    retry until `RAN control plane listener started`; then launch the UE and wait
    for `PDU session establishment complete`.
12. **Trigger NR-DC** — `POST /api/gnb/ue/nrdc` to the master gNB API with the
    UE's IMSI. This shortcuts the standard 3GPP SN-Addition (no real
    MeasurementReport); the SN identity is statically configured in
    `gnb-dc-dynamic-master.yaml`. SMF then installs the DC FAR via PFCP.
13. **Force DL traffic** — ping *toward* the UE (from `dn-ns`, or to `8.8.8.8`
    from the UE ns otherwise) so downlink packets traverse UPF-U's
    `packet_handler` and `DL path select` actually fires.
14. **Assert** — count the four log strings and print PASS / PARTIAL / FAIL.

---

## 4. Prerequisites (the script does NOT do these for you)

- Build everything:
  - `cd L25GC-plus && make nfs`
  - `cd NFs/onvm-upf && make`
  - `cd free-ran-ue && make bin`
- Hugepages + ONVM (once per boot):
  ```bash
  sudo sysctl -w vm.nr_hugepages=2048
  sudo mkdir -p /mnt/huge && sudo mount -t hugetlbfs nodev /mnt/huge
  ```
- `mongod` running with subscriber `imsi-208930000000001` provisioned
  (the script will insert it if absent, but mongod must be reachable).
- `sudo` access (namespaces, NIC/AF_PACKET binding, SCTP socket inspection).

---

## 5. Usage

```bash
cd /home/ubuntu/L25GC-plus
bash ./test_nrdc_local.sh
```

Run it from a normal interactive shell. All NF/RAN children are launched
detached with `</dev/null` and `sudo -n` so they do not grab the controlling
terminal (this avoids the "staircase" / raw-mode terminal corruption that
appears when backgrounded sudo'd children share the TTY).

Watch logs in a second shell while it runs:

```bash
tail -f log/upf_u.log log/upf_c.log log/smf.log
```

### Tunable environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AMF_MAX_ATTEMPTS` | `3` | AMF stability-retry count. |
| `PFCP_WAIT_SECS` | `90` | Max wait for SMF↔UPF PFCP association. |
| `PDU_WAIT_SECS` | `60` | Max wait for UE PDU session. |
| `GNB_WAIT_SECS` / `GNB_RETRIES` | `12` / `5` | gNB readiness wait & retries. |
| `ONVM_AF_PACKET_ACCESS_IFACE` | `brHost` | ONVM access-side iface. |
| `ONVM_AF_PACKET_CORE_IFACE` | `brDN` | ONVM core-side iface (also gates local DN ns). |
| `GO125` | `.cache/bin/go1.25.5` | Go toolchain for the subscriber inserter. |
| `L25GC` / `RAN` | script dir / `./free-ran-ue` | Repo locations. |

---

## 6. Stopping / cleanup

```bash
sudo bash scripts/run/stop_cn.sh                 # kill NFs + drop NF Mongo collections
sudo pkill -f free-ran-ue                          # kill gNBs + UE
sudo pkill -f onvm_mgr                              # kill ONVM manager
sudo bash free-ran-ue/script/namespace-script/free-ran-ue-dc-namespace.sh down
```

Config files are auto-restored on exit, so you do not need to undo the staging.

---

## 7. Caveats / common failure causes

- **`dc_gnb_ip` gates the whole feature.** In `NFs/onvm-upf/5gc/upf_u/config/upf_u.yaml`
  the `nrdc.dc_gnb_ip` must point at the secondary gNB N3 (`10.0.1.3` here). The
  script stages this automatically; if you run UPF-U by hand, set it or the
  `DL path select` code never runs.
- **AMF flakiness** is expected and handled — if you see "AMF crashed during
  stability window; retrying", that is the retry loop doing its job, not a bug.
  Most often the cause is stale ONVM shared memory from a previous run; the clean
  stage usually clears it.
- **PARTIAL (upserts but no selects)** usually means either NR-DC activation did
  not add the DC FAR (`grep 'Activate DCTunnel' log/smf.log`), `DcEnabled` is 0
  (`grep 'NR-DC ECMP enabled' log/upf_u.log`), or no DL traffic reached UPF-U
  (`cat log/ue-ping.log` / `log/dn-ping.log`).
- **FAIL (no DL lines)** points at an earlier stage: UE never registered
  (`log/ue.log`), gNB could not reach AMF, UPF-C never got PFCP
  (`grep PFCPSession log/upf_c.log`), or the NR-DC trigger curl failed (its
  response is printed in the trigger step).

All per-NF logs land in `log/` (`amf.log`, `nrf.log`, `smf.log`, `upf_c.log`,
`upf_u.log`, `onvm_mgr.log`, `gnb-master.log`, `gnb-secondary.log`, `ue.log`).
