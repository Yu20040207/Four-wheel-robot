"""Build the actual chassis C modules for a host-only R1 regression run."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MODULES = (
    "HAREWARE/USART2_HANDLER/usart2_handler.c",
    "HAREWARE/CONTROL/control.c",
    "BALANCE/CONCTRL/conctrl.c",
    "HAREWARE/USART_X/usart_x.c",
    "HAREWARE/LineFollow/LineFollow.c",
    "HAREWARE/AVOIDANCE/avoidance.c",
    "HAREWARE/VOICE_CONTROL/voice_control.c",
    "HAREWARE/MOTOR/motor.c",
)
INCLUDES = tuple(dict.fromkeys(str(Path(p).parent) for p in MODULES))
WRAPPER_TAILS = {
    "conctrl.c": """
void host_seed_pi(float pwm, float bias) {
    unsigned n;
    for (n = 0; n < 4; ++n) {
        velocity_pi_state[n].pwm = pwm;
        velocity_pi_state[n].last_bias = bias;
    }
}
int host_pi_is_zero(void) {
    unsigned n;
    for (n = 0; n < 4; ++n)
        if (velocity_pi_state[n].pwm != 0 || velocity_pi_state[n].last_bias != 0) return 0;
    return 1;
}
void host_set_fault(unsigned value) { motor_safety_latched = value ? 1 : 0; }
unsigned host_get_fault(void) { return motor_safety_latched; }
""",
    "LineFollow.c": """
int host_lf_is_clean(void) {
    return sensor_levels == 0 && new_data_available == 0 && sensor_sample_count == 0 &&
        sensor_history[0] == 0 && sensor_history[1] == 0 && sensor_history[2] == 0 &&
        filtered_error == 0 && last_error == 0 && last_line_error == 0 &&
        turn_output == 0 && lost_line_count == 0 && debug_frame_count == 0;
}
""",
    "usart2_handler.c": """
int host_uart2_is_clean(void) {
    return rx_index == 0 && rx_invalid == 0 && start_ready == 0 &&
        data_ready == 0 && chassis_data_ready == 0 &&
        ultrasonic_updated == 0 && chassis_cmd_updated == 0;
}
""",
}


def run(command, **kwargs):
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=HERE.parents[2],
                        help="Actual chassis root or a complete staged chassis tree")
    parser.add_argument("--cc", default=shutil.which("gcc") or r"C:\msys64\ucrt64\bin\gcc.exe")
    parser.add_argument("--compile-only", action="store_true",
                        help="Compile production wrappers/stubs only; do not link or execute")
    parser.add_argument("--case", action="append", help="Run only the named case(s)")
    args = parser.parse_args()
    root = args.source_root.resolve()
    missing = [p for p in MODULES if not (root / p).is_file()]
    if missing:
        parser.error("Incomplete source tree: " + ", ".join(missing))
    sources = [root / p for p in MODULES]
    headers = [p for folder in INCLUDES for p in (root / folder).glob("*.h")]
    tracked = sources + headers
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    print(f"Host C source root: {root}", flush=True)
    for p in sources:
        print(f"  {p.relative_to(root)} sha256={hashes[p]}", flush=True)
    with tempfile.TemporaryDirectory(prefix="stm32_r1_host_") as temporary:
        build = Path(temporary)
        wrappers = []
        for n, source in enumerate(sources):
            wrapper = build / f"module_{n}.c"
            # Forward slashes avoid accidental C escapes in a Windows include path.
            wrapper.write_text(f'#include "{source.as_posix()}"\n' +
                               WRAPPER_TAILS.get(source.name, ""), encoding="utf-8")
            wrappers.append(wrapper)
        common = [args.cc, "-std=c99", "-O0", "-g", "-Wall", "-Wextra",
                  "-Werror=implicit-function-declaration", "-ffunction-sections", "-fdata-sections",
                  "-I", str(HERE / "stubs"), "-I", str(HERE)]
        for folder in INCLUDES:
            common += ["-I", str(root / folder)]
        environment = dict(os.environ)
        compiler_dir = str(Path(args.cc).resolve().parent)
        environment["PATH"] = compiler_dir + os.pathsep + environment.get("PATH", "")
        objects = []
        for n, source in enumerate(wrappers + [HERE / "host_hal.c"]):
            obj = build / f"module_{n}.o"
            run(common + ["-c", str(source), "-o", str(obj)], env=environment)
            objects.append(obj)
        if args.compile_only:
            print("Production modules and HAL stubs compiled; no R1 tests executed.", flush=True)
        else:
            executable = build / ("test_r1.exe" if os.name == "nt" else "test_r1")
            run(common + [str(HERE / "test_r1.c"), *map(str, objects),
                          "-Wl,--gc-sections", "-lm", "-o", str(executable)], env=environment)
            listed = run([str(executable), "--list"], capture_output=True, env=environment)
            cases = args.case or listed.stdout.splitlines()
            for case in cases:
                run([str(executable), case], env=environment)
            print(f"PASS: {len(cases)} isolated actual-C R1 cases.", flush=True)
        changed = [str(p.relative_to(root)) for p, digest in hashes.items()
                   if hashlib.sha256(p.read_bytes()).hexdigest() != digest]
        if changed:
            raise RuntimeError("Source changed during host verification: " + ", ".join(changed))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
