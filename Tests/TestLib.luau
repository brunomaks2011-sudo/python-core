-- Minimal test harness for Lune.
local TestLib = {}

local results = { passed = 0, failed = 0, failures = {} }

function TestLib.test(name: string, fn: () -> ())
	local ok, err = pcall(fn)
	if ok then
		results.passed += 1
		print("  ok   " .. name)
	else
		results.failed += 1
		table.insert(results.failures, { name = name, err = tostring(err) })
		print("  FAIL " .. name .. "\n       " .. tostring(err))
	end
end

local function fmt(v: any): string
	if type(v) == "table" then
		local parts = {}
		for k, x in v do
			table.insert(parts, tostring(k) .. "=" .. tostring(x))
		end
		return "{" .. table.concat(parts, ",") .. "}"
	end
	return tostring(v)
end

function TestLib.eq(actual: any, expected: any, msg: string?)
	if actual ~= expected then
		error(string.format("%sexpected %s, got %s", if msg then msg .. ": " else "", fmt(expected), fmt(actual)), 2)
	end
end

function TestLib.near(actual: number, expected: number, eps: number, msg: string?)
	if math.abs(actual - expected) > eps then
		error(string.format("%sexpected %s +/- %s, got %s", if msg then msg .. ": " else "", tostring(expected), tostring(eps), tostring(actual)), 2)
	end
end

function TestLib.truthy(v: any, msg: string?)
	if not v then
		error((msg or "expected truthy value") .. ", got " .. fmt(v), 2)
	end
end

function TestLib.results()
	return results
end

return TestLib
