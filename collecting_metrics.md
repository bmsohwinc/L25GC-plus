## About the tools
There are 2 tools in the ONVM framework:
- CPU Utilization per scope (per function and within functions)
- Packet Timestamping (per packet and per function)

## To enable CPU Utilization per scope
1. First decide a scope you desire to measure and add a unique key to the below enum in `onvm/onvm_nflib/onvm_prof.h`:
```c
enum onvm_prof_key {
        ONVM_PROF_UPFU_PACKET_HANDLER = 0,
        // Add your new key here
        ONVM_PROF_KEY_COUNT
};
```

2. And add it to this array in `onvm/onvm_nflib/onvm_prof.c`:
```c
static const char *const onvm_prof_key_names[ONVM_PROF_KEY_COUNT] = {
        [ONVM_PROF_UPFU_PACKET_HANDLER] = "upf_u.packet_handler",       
        // Add your new key here in similar format
};
```

3. Then, add the below macro to the scope you desire to measure:
```c
ONVM_PROFILE_SCOPE(ONVM_PROF_UPFU_PACKET_HANDLER);
```

## To enable Packet Timestamping
1. Add the below macro at the point you desire to record with a unique key:
```c
ONVM_PKT_TS("nf.rx_dequeue", pkts[i]);
// See example in onvm/onvm_nflib/onvm_nflib.c in function onvm_nflib_dequeue_packets()
```

## Change in command for running the ONVM manager and NFs for timestamp tool.
- **Note**: The only change is adding the stderr redirection to the log file. The rest of the command remains the same.
1. **Terminal 1: Run ONVM Manager**
    ```bash
    cd ~/L25GC-plus/
    ./scripts/run/run_onvm_mgr.sh -a "<N3_IF_PCIE> <N6_IF_PCIE>" 2> /tmp/onvm_pkt_ts_mgr.log
    ```

2. **Terminal 2: Run UPF-U**
    ```bash
    cd ~/L25GC-plus/
    ./scripts/run/run_upf_u.sh 1 ./NFs/onvm-upf/5gc/upf_u/config/upf_u.yaml 2> /tmp/onvm_pkt_ts_upf_u.log
    ```

3. **Terminal 3: Run UPF-C**
    ```bash
    cd ~/L25GC-plus/
    ./scripts/run/run_upf_c.sh 2 ./NFs/onvm-upf/5gc/upf_c/config/upfcfg.yaml 2> /tmp/onvm_pkt_ts_upf_c.log
    ```
4. The other NFs can be run as before without any change in the command.

## To collect the final metrics:
1. Run the script `scripts/metrics/reset.sh` which automatically merges different logs into single file for each of the above tools in CN node:
- **Note**: This script will also stop all NFs. Modify as per your requirement if you want to keep the NFs running.

2. `scp` the merged logs to your local machine for further analysis.
```sh
# Assuming you are in the fabric_config directory with relevant ssh_config and slice_key files:
scp -F ./ssh_config -i ./slice_key \
'ubuntu@[2605:2800:2011:201:f816:3eff:fe55:40bf]:/home/ubuntu/L25GC-plus/merged_20260708_204501.log' \
./your/local/logs/
```

3. The script `scripts/metrics/analyze_simple_onvm_packet_timelines.py` can be used to analyze the packet timestamping logs. 
- It will generate two CSV files: 
  - `packet_timeline.csv`: Contains the timeline of packets with timestamps.
  - `example_packet_timelines.txt`: Simpler view of the packet timelines for quick reference.

## Final notes
- The timestamp tool works best for speeds like 1 packet per second, as it logs every packet's timestamp. For higher speeds, please wait till I find something.
    - You can disable the timestamp tool by setting `ONVM_PKT_TRACE_PRINT` to 0 in `onvm/onvm_nflib/onvm_pkt_trace_print.h`.
- The CPU util tool can be used for any speed.
