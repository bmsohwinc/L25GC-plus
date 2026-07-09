WORK_DIR=$HOME

cd ~/L25GC-plus/

./scripts/run/stop_cn.sh

sudo pkill -f './bin/amf|./bin/smf|./bin/nrf|./bin/nssf|./bin/ausf|./bin/udm|./bin/udr|./bin/pcf|./bin/chf'

echo "[I] Stopped all L25GC+ NFs and killed any remaining processes."

sudo pkill -f mongod

echo "[I] Stopped MongoDB service."

sleep 2

sudo systemctl enable mongod

sleep 2

sudo systemctl start mongod

echo "[I] Restarted MongoDB service."

cd $WORK_DIR

mkdir -p $WORK_DIR/logs

timestamp=$(date +"%Y%m%d_%H%M%S")
ts_output="merged_${timestamp}.log"
cpu_output="cpu_usage_${timestamp}.csv"

# Merge packet timestamp logs from different NFs
head -n 1 /tmp/onvm_pkt_ts_mgr.log > "$ts_output"
tail -n +2 /tmp/onvm_pkt_ts_mgr.log >> "$ts_output"
tail -n +2 /tmp/onvm_pkt_ts_upf_u.log >> "$ts_output"
tail -n +2 /tmp/onvm_pkt_ts_upf_c.log >> "$ts_output"

# Save CPU usage statistics to a separate CSV file
cp /tmp/onvm_prof_stats.csv "$cpu_output"

echo "Logs saved to $ts_output and $cpu_output in $WORK_DIR/logs"

rm -rf /tmp/onvm_pkt_ts_mgr.log
rm -rf /tmp/onvm_pkt_ts_upf_u.log
rm -rf /tmp/onvm_pkt_ts_upf_c.log
rm -rf /tmp/onvm_prof_stats.csv

echo "Temporary log files removed."
