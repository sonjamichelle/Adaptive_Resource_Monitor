# The client sends a single dot for each observation over the existing channel.
export LC_ALL=C
os=$(uname -sr)
nvidia=$(command -v nvidia-smi || :)
sample() {
    printf '@arm-begin\nos\t%s\n' "$os"
    while read -r name value; do
        case "$name" in
            cpu|cpu[0-9]*) printf 'cpu\t%s\t%s\n' "$name" "$value";;
            btime) printf 'boot\t%s\n' "$value";;
        esac
    done < /proc/stat
    while read -r name value unit; do
        case "$name" in
            MemTotal:|MemAvailable:|SwapTotal:|SwapFree:|Committed_AS:|CommitLimit:)
                printf 'ram\t%s\t%s\n' "${name%:}" "$value";;
        esac
    done < /proc/meminfo
    model= frequency= physical= core= processor=
    while IFS=: read -r key value; do
        case "${key// /}" in
            processor*) processor=$value;;
            modelname*|Hardware*) [[ -n $model ]] || model=$value;;
            cpuMHz*) [[ -n $frequency ]] || frequency=$value;;
            physicalid*) physical=$value;;
            coreid*) core=$value;;
            '') [[ -z $processor ]] || printf 'core\t%s\t%s\t%s\n' "$processor" "$physical" "$core"
                physical= core= processor=;;
        esac
    done < /proc/cpuinfo
    [[ -z $processor ]] || printf 'core\t%s\t%s\t%s\n' "$processor" "$physical" "$core"
    printf 'cpuinfo\t%s\t%s\n' "$model" "$frequency"
    for sensor in /sys/class/hwmon/hwmon*; do
        [[ -r $sensor/name ]] || continue
        read -r driver < "$sensor/name"
        case "$driver" in
            coretemp|k10temp|zenpower)
                temp= power=
                [[ ! -r $sensor/temp1_input ]] || read -r temp < "$sensor/temp1_input"
                [[ ! -r $sensor/power1_input ]] || read -r power < "$sensor/power1_input"
                printf 'cpusensor\t%s\t%s\n' "$temp" "$power";;
        esac
    done
    while read -r major minor dev rest; do
        [[ -d /sys/block/$dev && -e /sys/block/$dev/device ]] || continue
        printf 'disk\t%s\t%s\n' "$dev" "$rest"
    done < /proc/diskstats
    while IFS=: read -r dev rest; do
        [[ -n $rest ]] || continue
        dev=${dev//[[:space:]]/}
        path=/sys/class/net/$dev
        [[ -d $path ]] || continue
        speed= state= physical=0
        [[ ! -e $path/device ]] || physical=1
        [[ ! -r $path/operstate ]] || read -r state < "$path/operstate"
        { [[ ! -r $path/speed ]] || read -r speed < "$path/speed"; } 2>/dev/null
        printf 'net\t%s\t%s\t%s\t%s\t%s\n' "$dev" "$physical" "$state" "$speed" "$rest"
    done < /proc/net/dev
    for path in /sys/class/drm/card[0-9]*; do
        [[ ${path##*/} =~ ^card[0-9]+$ && -r $path/device/vendor ]] || continue
        dev=$path/device
        vendor= id= slot= busy= used= total= temperature= clock= memory_clock= power= cap=
        read -r vendor < "$dev/vendor"
        if [[ $vendor == 0x10de && -n $nvidia ]]; then continue; fi
        [[ ! -r $dev/device ]] || read -r id < "$dev/device"
        if [[ -r $dev/uevent ]]; then
            while IFS== read -r key value; do
                [[ $key != PCI_SLOT_NAME ]] || slot=$value
            done < "$dev/uevent"
        fi
        [[ ! -r $dev/gpu_busy_percent ]] || read -r busy < "$dev/gpu_busy_percent"
        [[ ! -r $dev/mem_info_vram_used ]] || read -r used < "$dev/mem_info_vram_used"
        [[ ! -r $dev/mem_info_vram_total ]] || read -r total < "$dev/mem_info_vram_total"
        [[ ! -r $dev/pp_dpm_sclk ]] || while read -r _ val tag; do
            [[ $tag != '*' ]] || clock=${val%[Mm][Hh][Zz]}
        done < "$dev/pp_dpm_sclk"
        [[ ! -r $dev/pp_dpm_mclk ]] || while read -r _ val tag; do
            [[ $tag != '*' ]] || memory_clock=${val%[Mm][Hh][Zz]}
        done < "$dev/pp_dpm_mclk"
        for sensor in "$dev"/hwmon/hwmon*; do
            [[ -d $sensor ]] || continue
            [[ ! -r $sensor/temp1_input ]] || read -r temperature < "$sensor/temp1_input"
            [[ ! -r $sensor/power1_average ]] || read -r power < "$sensor/power1_average"
            [[ ! -r $sensor/power1_cap ]] || read -r cap < "$sensor/power1_cap"
            break
        done
        printf 'drm\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "${slot:-${path##*/}}" "$vendor" "$id" "$busy" "$used" "$total" "$temperature" \
            "$clock" "$memory_clock" "$power,$cap"
    done
    if [[ -n $nvidia ]] && command -v timeout >/dev/null; then
        timeout 2 "$nvidia" --format=csv,noheader,nounits \
            --query-gpu=pci.bus_id,name,utilization.gpu,memory.used,memory.total,temperature.gpu,clocks.gr,clocks.mem,power.draw,power.limit,fan.speed,utilization.encoder,utilization.decoder \
            2>/dev/null | while IFS= read -r gpu; do printf 'nvidia\t%s\n' "$gpu"; done
    fi
    printf '@arm-end\n'
}
while IFS= read -r action; do
    [[ $action == . ]] || break
    sample
done
