// luau-check: type-check Roblox Luau files with Luau's own Analysis engine.
// Usage: luau-check <definitions.d.luau> [--quiet-nil] <file.luau>...
// Cross-module `require` calls are replaced by `any`, so each file is checked
// on its own against the Roblox API definitions.
use luau_analyze::{CheckOptions, Checker};
use regex::Regex;
use std::{env, fs, process, time::Duration};

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.len() < 2 {
        eprintln!("usage: luau-check <defs.d.luau> [--quiet-nil] <files...>");
        process::exit(2);
    }
    let defs = fs::read_to_string(&args[0]).expect("read definitions");
    let mut checker = Checker::new().expect("checker");
    if let Err(e) = checker.add_definitions(&defs) {
        eprintln!("failed to load definitions: {e:?}");
        process::exit(3);
    }
    let quiet_nil = args.iter().any(|a| a == "--quiet-nil");
    let req = Regex::new(r"\brequire\s*\(").unwrap();
    // exported types of other modules are unknown in single-file mode: treat as any
    let xtype = Regex::new(r"\b(SoldierRegistry|BuildingLayout|Rig|VehiclePhysics|Hits|DestructionService|VehicleService|CombatService|MapInfo|DominationMode|Util|Squad|Bot|Commander|Navigator)\.(Soldier|Piece|State|Input|Rigged|HitInfo|Stats|Vehicle|PieceRec|BuildingRec|Info|Projectile|Point|Event|Signal|Occupancy|PointDef|SpawnOption|Brain|Order)\b").unwrap();
    let mut total = 0usize;
    for file in args.iter().skip(1).filter(|a| !a.starts_with("--")) {
        let src = match fs::read_to_string(file) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("{file}: cannot read: {e}");
                continue;
            }
        };
        // drop mode comments: the checker is strict-only
        let src = src.replace("--!nonstrict", "--").replace("--!nocheck", "--");
        let src = req.replace_all(&src, "(nil :: any)(").to_string();
        let src = xtype.replace_all(&src, "any").to_string();
        let opts = CheckOptions { timeout: Some(Duration::from_secs(60)), module_name: Some(file), ..Default::default() };
        match checker.check_with_options(&src, opts) {
            Ok(res) => {
                for d in res.diagnostics {
                    let m = &d.message;
                    if quiet_nil && (m.contains("could be nil") || m.contains("might be nil") || m.contains("nil-able")) {
                        continue;
                    }
                    total += 1;
                    println!("{}:{}:{}: {:?}: {}", file, d.line + 1, d.col + 1, d.severity, m.replace('\n', " "));
                }
                if res.timed_out {
                    println!("{file}: timed out");
                }
            }
            Err(e) => println!("{file}: checker error: {e:?}"),
        }
    }
    eprintln!("{total} diagnostic(s)");
}
