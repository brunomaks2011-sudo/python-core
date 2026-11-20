-- Emulates Roblox's ModuleScript system under Lune so pure shared modules that
-- use `require(script.Parent.Foo)` can be unit-tested outside Roblox.
--   local Shim = require("../RobloxShim")
--   local Util = Shim.load("Assets/Scripts/Shared/Util")
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local roblox = require("@lune/roblox")
local task = require("@lune/task")

local Shim = {}

local cache: { [string]: any } = {}

local function isDir(p: string): boolean
	return fs.isDir(p)
end

local function fileFor(p: string): string?
	for _, ext in { ".luau", ".lua" } do
		if fs.isFile(p .. ext) then
			return p .. ext
		end
	end
	if isDir(p) then
		for _, init in { "/init.luau", "/init.lua" } do
			if fs.isFile(p .. init) then
				return p .. init
			end
		end
	end
	return nil
end

-- A proxy object standing in for an Instance at a filesystem path.
local function proxy(path: string)
	local obj = { __path = path }
	return setmetatable(obj, {
		__index = function(_, key)
			if key == "Parent" then
				local parent = string.match(path, "^(.*)/[^/]+$") or "."
				return proxy(parent)
			elseif key == "Name" then
				return string.match(path, "([^/]+)$")
			end
			return proxy(path .. "/" .. key)
		end,
	})
end

local function makeEnv(modulePath: string)
	local env = {}
	env.script = proxy(modulePath)
	env.require = function(target)
		if type(target) == "table" and rawget(target, "__path") then
			return Shim.load(rawget(target, "__path"))
		elseif type(target) == "string" then
			return Shim.load(target)
		end
		error("unsupported require target " .. tostring(target))
	end
	env.Vector3 = roblox.Vector3
	env.Vector2 = roblox.Vector2
	env.CFrame = roblox.CFrame
	env.Color3 = roblox.Color3
	env.UDim2 = roblox.UDim2
	env.UDim = roblox.UDim
	env.NumberRange = roblox.NumberRange
	env.Random = roblox.Random
	env.Enum = roblox.Enum
	env.Instance = roblox.Instance
	env.task = task
	env.tick = os.clock
	env.time = os.clock
	return setmetatable(env, { __index = _G })
end

function Shim.load(path: string): any
	local file = fileFor(path)
	assert(file, "module not found: " .. path)
	if cache[file] ~= nil then
		return cache[file]
	end
	local source = fs.readFile(file)
	-- the module's own instance path is the file path without the extension
	local modulePath = string.gsub(string.gsub(file, "/init%.luau?$", ""), "%.luau?$", "")
	local fn = luau.load(source, { debugName = file, environment = makeEnv(modulePath) })
	local result = fn()
	cache[file] = result
	return result
end

return Shim
