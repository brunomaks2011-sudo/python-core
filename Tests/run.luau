-- Lune test runner:  lune run Tests/run
local fs = require("@lune/fs")
local process = require("@lune/process")
local T = require("./TestLib")

local specs = {}
for _, name in fs.readDir("Tests/unit") do
	if string.match(name, "%.spec%.luau$") then
		table.insert(specs, name)
	end
end
table.sort(specs)

for _, name in specs do
	print("\n" .. name)
	local ok, err = pcall(require, "./unit/" .. string.gsub(name, "%.luau$", ""))
	if not ok then
		print("  FAIL (load error) " .. tostring(err))
		T.results().failed += 1
	end
end

local r = T.results()
print(string.format("\n%d passed, %d failed", r.passed, r.failed))
process.exit(if r.failed == 0 then 0 else 1)
