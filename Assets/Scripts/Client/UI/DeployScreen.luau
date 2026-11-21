--!strict
-- Deployment screen: faction (BLUE / RED themed UI), infantry class, spawn
-- location on the map, and an optional vehicle from the motor pool.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local Theme = require(script.Parent.Theme)
local Minimap = require(script.Parent.Minimap)
local ClientState = require(script.Parent.Parent.ClientState)

local DeployScreen = {}

local player = Players.LocalPlayer
local gui: ScreenGui
local state: Folder
local team = 1
local role = "rifleman"
local spawnId = "HQ"
local vehicleKind: string? = nil
local refs: { [string]: any } = {}
local options: { [string]: any } = { spawns = {}, vehicles = {}, respawnIn = 0 }
DeployScreen.onDeployed = nil :: (() -> ())?

local function accent(): Color3
	return Theme.team(team)
end

local function restyle()
	local a = accent()
	refs.header.BackgroundColor3 = Theme.teamDark(team)
	refs.deploy.BackgroundColor3 = a
	refs.title.Text = string.upper(Constants.TEAM_ARMY[team]) .. "  -  DEPLOYMENT"
	for t, card in refs.factionCards do
		card.stroke.Color = if t == team then Theme.team(t) else Theme.Line
		card.stroke.Thickness = if t == team then 3 else 1
		card.frame.BackgroundColor3 = if t == team then Theme.teamDark(t) else Theme.Panel
	end
	for r, card in refs.roleCards do
		card.stroke.Color = if r == role then a else Theme.Line
		card.frame.BackgroundColor3 = if r == role then Theme.teamDark(team) else Theme.Panel
	end
	refs.mapFrame.UIStroke.Color = a
end

local function refreshOptions()
	local ok, result = pcall(function()
		return Net.func("GetDeployOptions"):InvokeServer(team)
	end)
	if ok and type(result) == "table" then
		options = result
	end
	-- spawn markers on the map
	for _, m in refs.spawnMarkers do
		m:Destroy()
	end
	refs.spawnMarkers = {}
	local valid = false
	for _, sp in options.spawns do
		local b = Instance.new("TextButton")
		b.AnchorPoint = Vector2.new(0.5, 0.5)
		b.Size = UDim2.fromOffset(if sp.kind == "hq" then 46 else 36, 24)
		b.Position = refs.map:toCanvas(sp.x, sp.z) + UDim2.fromOffset(0, -26)
		b.Text = if sp.kind == "hq" then "HQ" elseif sp.kind == "point" then string.sub(sp.id, 2) else "V"
		b.Font = Theme.FontBlack
		b.TextSize = 14
		b.TextColor3 = Color3.new(1, 1, 1)
		b.BackgroundColor3 = if not sp.available then Color3.fromRGB(70, 70, 70) elseif sp.id == spawnId then Theme.Gold else accent()
		b.AutoButtonColor = sp.available
		b.ZIndex = 20
		Theme.corner(b, 4)
		b.Parent = refs.map.markers
		b.MouseButton1Click:Connect(function()
			if sp.available then
				spawnId = sp.id
				refreshOptions()
			end
		end)
		table.insert(refs.spawnMarkers, b)
		if sp.id == spawnId and sp.available then
			valid = true
		end
	end
	if not valid then
		spawnId = "HQ"
	end
	-- vehicle list
	for _, ch in refs.vehicleList:GetChildren() do
		if ch:IsA("TextButton") then
			ch:Destroy()
		end
	end
	local none = Theme.button(refs.vehicleList, "None", "ON FOOT", UDim2.new(1, -8, 0, 30), UDim2.new(0, 0, 0, 0), accent())
	none.LayoutOrder = 0
	none.TextSize = 14
	if vehicleKind == nil then
		none.TextColor3 = Theme.Gold
	end
	none.MouseButton1Click:Connect(function()
		vehicleKind = nil
		refreshOptions()
	end)
	for i, v in options.vehicles do
		local b = Theme.button(refs.vehicleList, v.kind, "", UDim2.new(1, -8, 0, 30), UDim2.new(0, 0, 0, 0), accent())
		b.LayoutOrder = i
		b.TextSize = 13
		b.TextXAlignment = Enum.TextXAlignment.Left
		local status = if v.available > 0 then string.format("%d/%d", v.available, v.total) elseif v.respawn > 0 then string.format("%ds", v.respawn) else "IN USE"
		b.Text = string.format("   %s  -  %s   [%s]", v.name, v.category, status)
		b.TextColor3 = if v.available <= 0 then Theme.TextDim elseif vehicleKind == v.kind then Theme.Gold else Theme.Text
		b.MouseButton1Click:Connect(function()
			if v.available > 0 then
				vehicleKind = v.kind
				refreshOptions()
			end
		end)
	end
	restyle()
end

local function build()
	gui = Theme.screen("Deploy", 20)
	gui.Enabled = false
	local bg = Theme.frame(gui, "Bg", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), Theme.Bg, 0.25)
	local header = Theme.frame(bg, "Header", UDim2.new(1, 0, 0, 64), UDim2.fromScale(0, 0), Theme.BlueDark, 0.1)
	refs.header = header
	refs.title = Theme.label(header, "Title", "DEPLOYMENT", UDim2.new(0.6, 0, 1, 0), UDim2.new(0, 24, 0, 0), 28, Theme.Text, Theme.FontBlack)
	refs.timers = Theme.label(header, "Timers", "", UDim2.new(0.4, -24, 1, 0), UDim2.new(0.6, 0, 0, 0), 18, Theme.Text, Theme.FontBold)
	refs.timers.TextXAlignment = Enum.TextXAlignment.Right
	refs.timers.RichText = true

	-- faction column -------------------------------------------------------------
	local left = Theme.frame(bg, "Left", UDim2.new(0, 360, 1, -150), UDim2.new(0, 20, 0, 80), Theme.Bg, 1)
	Theme.label(left, "FactionTitle", "FACTION", UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, 0), 16, Theme.TextDim, Theme.FontBold)
	refs.factionCards = {}
	for i, t in { 1, 2 } do
		local f = Theme.frame(left, "Faction" .. t, UDim2.new(0.5, -6, 0, 90), UDim2.new((i - 1) * 0.5, (i - 1) * 6, 0, 26), Theme.Panel, 0.05)
		Theme.corner(f, 6)
		local stroke = Theme.stroke(f, Theme.Line, 1, 0)
		local strip = Theme.frame(f, "Strip", UDim2.new(1, 0, 0, 6), UDim2.new(0, 0, 0, 0), Theme.team(t), 0)
		local _ = strip
		Theme.label(f, "Name", string.upper(Constants.TEAM_ARMY[t]), UDim2.new(1, -16, 0, 26), UDim2.new(0, 8, 0, 12), 18, Theme.team(t), Theme.FontBlack)
		local info = Theme.label(f, "Info", "", UDim2.new(1, -16, 0, 40), UDim2.new(0, 8, 0, 40), 13, Theme.TextDim, Theme.Font)
		info.TextWrapped = true
		info.TextYAlignment = Enum.TextYAlignment.Top
		local btn = Instance.new("TextButton")
		btn.BackgroundTransparency = 1
		btn.Text = ""
		btn.Size = UDim2.fromScale(1, 1)
		btn.Parent = f
		btn.MouseButton1Click:Connect(function()
			if team ~= t then
				team = t
				vehicleKind = nil
				spawnId = "HQ"
				refreshOptions()
			end
		end)
		refs.factionCards[t] = { frame = f, stroke = stroke, info = info }
	end
	-- class list
	Theme.label(left, "ClassTitle", "CLASS", UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, 126), 16, Theme.TextDim, Theme.FontBold)
	refs.roleCards = {}
	for i, r in Defs.RoleOrder do
		local def = Defs.Roles[r]
		local f = Theme.frame(left, "Role" .. r, UDim2.new(1, 0, 0, 62), UDim2.new(0, 0, 0, 150 + (i - 1) * 68), Theme.Panel, 0.05)
		Theme.corner(f, 6)
		local stroke = Theme.stroke(f, Theme.Line, 1, 0)
		Theme.label(f, "Name", string.upper(def.name), UDim2.new(1, -16, 0, 20), UDim2.new(0, 10, 0, 4), 16, Theme.Text, Theme.FontBlack)
		local d = Theme.label(f, "Desc", def.desc, UDim2.new(1, -20, 0, 34), UDim2.new(0, 10, 0, 24), 12, Theme.TextDim, Theme.Font)
		d.TextWrapped = true
		d.TextYAlignment = Enum.TextYAlignment.Top
		local btn = Instance.new("TextButton")
		btn.BackgroundTransparency = 1
		btn.Text = ""
		btn.Size = UDim2.fromScale(1, 1)
		btn.Parent = f
		btn.MouseButton1Click:Connect(function()
			role = r
			restyle()
		end)
		refs.roleCards[r] = { frame = f, stroke = stroke }
	end

	-- map ---------------------------------------------------------------------
	local mapFrame = Theme.frame(bg, "MapFrame", UDim2.new(0, 560, 0, 560), UDim2.new(0.5, -230, 0, 80), Theme.Panel, 0)
	Theme.stroke(mapFrame, Theme.Blue, 2, 0)
	refs.mapFrame = mapFrame
	local info = require(ReplicatedStorage.Shared.MapInfo).get()
	local extent = math.max(info.playable.maxX, info.playable.maxZ) + 300
	refs.map = Minimap.new(mapFrame, UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), 560 / (extent * 2), false)
	refs.spawnMarkers = {}
	Theme.label(bg, "MapHint", "Select a spawn point on the map", UDim2.new(0, 560, 0, 20), UDim2.new(0.5, -230, 0, 646), 14, Theme.TextDim, Theme.Font)

	-- vehicles + deploy ------------------------------------------------------------
	local right = Theme.frame(bg, "Right", UDim2.new(0, 340, 1, -150), UDim2.new(1, -360, 0, 80), Theme.Bg, 1)
	Theme.label(right, "VehTitle", "VEHICLE (OPTIONAL)", UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, 0), 16, Theme.TextDim, Theme.FontBold)
	local list = Instance.new("ScrollingFrame")
	list.Name = "Vehicles"
	list.Size = UDim2.new(1, 0, 1, -140)
	list.Position = UDim2.new(0, 0, 0, 26)
	list.BackgroundTransparency = 1
	list.BorderSizePixel = 0
	list.ScrollBarThickness = 4
	list.AutomaticCanvasSize = Enum.AutomaticSize.Y
	list.CanvasSize = UDim2.new()
	list.Parent = right
	local ll = Instance.new("UIListLayout")
	ll.Padding = UDim.new(0, 4)
	ll.SortOrder = Enum.SortOrder.LayoutOrder
	ll.Parent = list
	refs.vehicleList = list
	refs.status = Theme.label(right, "Status", "", UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 1, -104), 15, Theme.Warn, Theme.FontBold)
	local deploy = Theme.button(right, "Deploy", "DEPLOY", UDim2.new(1, 0, 0, 60), UDim2.new(0, 0, 1, -76), Theme.Gold)
	deploy.TextSize = 28
	deploy.Font = Theme.FontBlack
	refs.deploy = deploy
	deploy.MouseButton1Click:Connect(function()
		if (options.respawnIn or 0) > 0.2 then
			return
		end
		refs.status.Text = "Deploying..."
		Net.event("Deploy"):FireServer({ team = team, role = role, spawn = spawnId, vehicle = vehicleKind })
	end)
	gui.Parent = player:WaitForChild("PlayerGui")
end

function DeployScreen.open()
	ClientState.inMenu = true
	gui.Enabled = true
	refs.status.Text = ""
	refreshOptions()
end

function DeployScreen.close()
	gui.Enabled = false
end

function DeployScreen.isOpen(): boolean
	return gui.Enabled
end

function DeployScreen.init()
	state = Net.matchState()
	build()
	Net.event("MatchEvent").OnClientEvent:Connect(function(e)
		if type(e) ~= "table" then
			return
		end
		if e.kind == "deployResult" then
			if e.ok then
				ClientState.team = team
				ClientState.role = role
				ClientState.deployed = true
				ClientState.inMenu = false
				DeployScreen.close()
				if DeployScreen.onDeployed then
					DeployScreen.onDeployed()
				end
			else
				refs.status.Text = e.reason or "Cannot deploy"
				refreshOptions()
			end
		end
	end)
	local acc = 0
	RunService.RenderStepped:Connect(function(dt)
		if not gui.Enabled then
			return
		end
		refs.map:update()
		acc += dt
		local rate = Util.num(state, "TickRate", 10)
		refs.timers.Text = string.format('<font color="#2F7BFF">BLUE %04d</font>   %s   <font color="#FF3B30">RED %04d</font>',
			math.floor((Util.num(state, "BlueTicks", 0)) / rate), Util.formatTime((Util.num(state, "Tick", 0)) / rate),
			math.floor((Util.num(state, "RedTicks", 0)) / rate))
		for t, card in refs.factionCards do
			local held = Util.num(state, if t == 1 then "BlueHeld" else "RedHeld", 0)
			local n = 0
			for _, p in Players:GetPlayers() do
				if p.Team and p.Team.Name == Constants.TEAM_OBJECT_NAME[t] then
					n += 1
				end
			end
			card.info.Text = string.format("%d players  |  %d flags held", n, held)
		end
		if acc > 1 then
			acc = 0
			options.respawnIn = math.max(0, (options.respawnIn or 0) - 1)
			refreshOptions()
		end
		local wait = options.respawnIn or 0
		refs.deploy.Text = if wait > 0.2 then string.format("DEPLOY IN %d", math.ceil(wait)) else "DEPLOY"
	end)
end

function DeployScreen.setTeam(t: number)
	team = t
end

return DeployScreen
