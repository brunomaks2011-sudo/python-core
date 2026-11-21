--!strict
-- In-game HUD. Everything domination-related reads the server's read-only
-- MatchState attributes, so it always shows the official timers.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local Theme = require(script.Parent.Theme)
local ClientState = require(script.Parent.Parent.ClientState)

local HUD = {}

local player = Players.LocalPlayer
local state: Folder
local gui: ScreenGui
local POINT_IDS = { "A", "B", "C" }

local refs: { [string]: any } = {}

local function teamBlock(parent: Instance, team: number, x: UDim2, alignRight: boolean)
	local color = Theme.team(team)
	local block = Theme.frame(parent, if team == 1 then "Blue" else "Red", UDim2.new(0, 290, 1, 0), x, Theme.Panel, 0.25)
	Theme.corner(block, 4)
	local strip = Theme.frame(block, "Strip", UDim2.new(0, 4, 1, 0), if alignRight then UDim2.new(1, -4, 0, 0) else UDim2.new(0, 0, 0, 0), color, 0)
	local _ = strip
	local name = Theme.label(block, "Name", if team == 1 then "BLUE TEAM" else "RED TEAM", UDim2.new(1, -24, 0, 18), UDim2.new(0, 12, 0, 4), 14, color, Theme.FontBlack)
	name.TextXAlignment = if alignRight then Enum.TextXAlignment.Right else Enum.TextXAlignment.Left
	local timer = Theme.label(block, "Timer", "0000 / 1000 SEC", UDim2.new(1, -24, 0, 26), UDim2.new(0, 12, 0, 20), 24, Theme.Text, Theme.FontBold)
	timer.TextXAlignment = name.TextXAlignment
	timer.Font = Enum.Font.RobotoMono
	local barBg = Theme.frame(block, "BarBg", UDim2.new(1, -24, 0, 6), UDim2.new(0, 12, 1, -14), Color3.fromRGB(40, 46, 54), 0)
	Theme.corner(barBg, 3)
	local bar = Theme.frame(barBg, "Bar", UDim2.new(0, 0, 1, 0), if alignRight then UDim2.new(1, 0, 0, 0) else UDim2.new(0, 0, 0, 0), color, 0)
	bar.AnchorPoint = if alignRight then Vector2.new(1, 0) else Vector2.new(0, 0)
	Theme.corner(bar, 3)
	local held = Theme.label(block, "Held", "0 FLAGS", UDim2.new(0, 120, 0, 16), if alignRight then UDim2.new(0, 12, 0, 4) else UDim2.new(1, -132, 0, 4), 13, Theme.TextDim, Theme.FontBold)
	held.TextXAlignment = if alignRight then Enum.TextXAlignment.Left else Enum.TextXAlignment.Right
	return { timer = timer, bar = bar, held = held }
end

local function pointBadge(parent: Instance, id: string, x: number)
	local badge = Theme.frame(parent, "Point" .. id, UDim2.new(0, 54, 0, 54), UDim2.new(0, x, 0, 3), Theme.PanelLight, 0.1)
	Theme.corner(badge, 6)
	local stroke = Theme.stroke(badge, Theme.Neutral, 2, 0)
	local fill = Theme.frame(badge, "Fill", UDim2.new(1, 0, 0, 0), UDim2.new(0, 0, 1, 0), Theme.Blue, 0.15)
	fill.AnchorPoint = Vector2.new(0, 1)
	Theme.corner(fill, 6)
	local letter = Theme.label(badge, "Letter", id, UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), 30, Theme.Text, Theme.FontBlack)
	letter.TextXAlignment = Enum.TextXAlignment.Center
	letter.ZIndex = 3
	local status = Theme.label(parent, "Status" .. id, "", UDim2.new(0, 70, 0, 14), UDim2.new(0, x - 8, 0, 60), 11, Theme.TextDim, Theme.FontBold)
	status.TextXAlignment = Enum.TextXAlignment.Center
	return { badge = badge, stroke = stroke, fill = fill, letter = letter, status = status }
end

local function build()
	gui = Theme.screen("HUD", 5)
	gui.Enabled = false
	-- domination panel ----------------------------------------------------------
	local top = Theme.frame(gui, "Domination", UDim2.new(0, 820, 0, 62), UDim2.new(0.5, -410, 0, 10), Theme.Bg, 1)
	refs.blue = teamBlock(top, 1, UDim2.new(0, 0, 0, 0), false)
	refs.red = teamBlock(top, 2, UDim2.new(1, -290, 0, 0), true)
	local mid = Theme.frame(top, "Points", UDim2.new(0, 220, 1, 0), UDim2.new(0.5, -110, 0, 0), Theme.Bg, 1)
	refs.points = {}
	for i, id in POINT_IDS do
		refs.points[id] = pointBadge(mid, id, (i - 1) * 74 + 10)
	end
	local info = Theme.frame(gui, "MatchInfo", UDim2.new(0, 400, 0, 20), UDim2.new(0.5, -200, 0, 96), Theme.Bg, 1)
	refs.clock = Theme.label(info, "Clock", "MATCH 00:00", UDim2.new(0.5, 0, 1, 0), UDim2.new(0, 0, 0, 0), 14, Theme.TextDim, Theme.FontBold)
	refs.clock.TextXAlignment = Enum.TextXAlignment.Right
	refs.flags = Theme.label(info, "Flags", "", UDim2.new(0.5, -12, 1, 0), UDim2.new(0.5, 12, 0, 0), 14, Theme.TextDim, Theme.FontBold)
	refs.sudden = Theme.label(gui, "SuddenDeath", "SUDDEN DEATH - TAKE THE MAJORITY OF FLAGS", UDim2.new(0, 500, 0, 22), UDim2.new(0.5, -250, 0, 118), 16, Theme.Warn, Theme.FontBlack)
	refs.sudden.TextXAlignment = Enum.TextXAlignment.Center
	refs.sudden.Visible = false
	refs.objective = Theme.label(gui, "Objective", "", UDim2.new(0, 600, 0, 22), UDim2.new(0.5, -300, 0, 140), 16, Theme.Gold, Theme.FontBold)
	refs.objective.TextXAlignment = Enum.TextXAlignment.Center
	refs.objective.TextStrokeTransparency = 0.6

	-- compass ---------------------------------------------------------------------
	local compass = Theme.frame(gui, "Compass", UDim2.new(0, 520, 0, 22), UDim2.new(0.5, -260, 0, 74), Theme.Bg, 0.6)
	compass.ClipsDescendants = true
	compass.Position = UDim2.new(0.5, -260, 1, -30)
	Theme.corner(compass, 4)
	refs.compass = compass
	refs.compassMarks = {}
	for k = 0, 23 do
		local deg = k * 15
		local label = if deg % 90 == 0 then ({ [0] = "N", [90] = "E", [180] = "S", [270] = "W" })[deg] else (if deg % 45 == 0 then tostring(deg) else "|")
		local l = Theme.label(compass, "M" .. k, label, UDim2.new(0, 40, 1, 0), UDim2.new(0, 0, 0, 0), if deg % 90 == 0 then 15 else 11, if deg % 90 == 0 then Theme.Text else Theme.TextDim, Theme.FontBold)
		l.TextXAlignment = Enum.TextXAlignment.Center
		refs.compassMarks[k] = { label = l, deg = deg }
	end
	refs.compassPoints = {}
	for _, id in POINT_IDS do
		local l = Theme.label(compass, "P" .. id, id, UDim2.new(0, 60, 1, 0), UDim2.new(0, 0, 0, 0), 14, Theme.Neutral, Theme.FontBlack)
		l.TextXAlignment = Enum.TextXAlignment.Center
		refs.compassPoints[id] = l
	end

	-- capture panel ------------------------------------------------------------------
	local cap = Theme.frame(gui, "Capture", UDim2.new(0, 360, 0, 54), UDim2.new(0.5, -180, 0.24, 0), Theme.Panel, 0.2)
	Theme.corner(cap, 6)
	Theme.stroke(cap, Theme.Line, 1, 0.5)
	cap.Visible = false
	refs.capture = cap
	refs.capText = Theme.label(cap, "Text", "", UDim2.new(1, -20, 0, 26), UDim2.new(0, 10, 0, 4), 18, Theme.Text, Theme.FontBlack)
	refs.capText.TextXAlignment = Enum.TextXAlignment.Center
	local capBg = Theme.frame(cap, "BarBg", UDim2.new(1, -20, 0, 10), UDim2.new(0, 10, 0, 34), Color3.fromRGB(40, 46, 54), 0)
	Theme.corner(capBg, 4)
	refs.capBar = Theme.frame(capBg, "Bar", UDim2.new(0.5, 0, 1, 0), UDim2.new(0, 0, 0, 0), Theme.Blue, 0)
	Theme.corner(refs.capBar, 4)

	-- player panel --------------------------------------------------------------------
	local pp = Theme.frame(gui, "Player", UDim2.new(0, 330, 0, 92), UDim2.new(0, 16, 1, -108), Theme.Panel, 0.25)
	Theme.corner(pp, 6)
	refs.faction = Theme.frame(pp, "Faction", UDim2.new(0, 6, 1, 0), UDim2.new(0, 0, 0, 0), Theme.Blue, 0)
	refs.roleText = Theme.label(pp, "Role", "", UDim2.new(1, -24, 0, 18), UDim2.new(0, 16, 0, 6), 14, Theme.TextDim, Theme.FontBold)
	local hpBg = Theme.frame(pp, "HPBg", UDim2.new(1, -90, 0, 14), UDim2.new(0, 16, 0, 30), Color3.fromRGB(40, 46, 54), 0)
	Theme.corner(hpBg, 3)
	refs.hpBar = Theme.frame(hpBg, "HP", UDim2.new(1, 0, 1, 0), UDim2.new(0, 0, 0, 0), Theme.Good, 0)
	Theme.corner(refs.hpBar, 3)
	refs.hpText = Theme.label(pp, "HPText", "100", UDim2.new(0, 60, 0, 18), UDim2.new(1, -68, 0, 28), 20, Theme.Text, Theme.FontBlack)
	local stBg = Theme.frame(pp, "StaminaBg", UDim2.new(1, -90, 0, 4), UDim2.new(0, 16, 0, 48), Color3.fromRGB(40, 46, 54), 0)
	refs.stBar = Theme.frame(stBg, "Stamina", UDim2.new(1, 0, 1, 0), UDim2.new(0, 0, 0, 0), Theme.Gold, 0)
	refs.vehicleRow = Theme.frame(pp, "Vehicle", UDim2.new(1, -24, 0, 26), UDim2.new(0, 16, 0, 58), Theme.Bg, 1)
	refs.vehicleName = Theme.label(refs.vehicleRow, "Name", "", UDim2.new(0.55, 0, 1, 0), UDim2.new(0, 0, 0, 0), 13, Theme.Text, Theme.FontBold)
	local vhBg = Theme.frame(refs.vehicleRow, "VBg", UDim2.new(0.45, -6, 0, 8), UDim2.new(0.55, 6, 0.5, -4), Color3.fromRGB(40, 46, 54), 0)
	refs.vhBar = Theme.frame(vhBg, "VH", UDim2.new(1, 0, 1, 0), UDim2.new(0, 0, 0, 0), Theme.Neutral, 0)
	refs.vehicleRow.Visible = false

	-- weapon panel --------------------------------------------------------------------
	local wp = Theme.frame(gui, "Weapon", UDim2.new(0, 280, 0, 92), UDim2.new(1, -296, 1, -108), Theme.Panel, 0.25)
	Theme.corner(wp, 6)
	refs.weaponName = Theme.label(wp, "Name", "", UDim2.new(1, -24, 0, 18), UDim2.new(0, 12, 0, 6), 14, Theme.TextDim, Theme.FontBold)
	refs.ammo = Theme.label(wp, "Ammo", "30", UDim2.new(0, 120, 0, 44), UDim2.new(0, 12, 0, 26), 40, Theme.Text, Theme.FontBlack)
	refs.reserve = Theme.label(wp, "Reserve", "/ 180", UDim2.new(0, 120, 0, 24), UDim2.new(0, 112, 0, 42), 20, Theme.TextDim, Theme.FontBold)
	refs.extra = Theme.label(wp, "Extra", "", UDim2.new(1, -24, 0, 16), UDim2.new(0, 12, 1, -22), 13, Theme.TextDim, Theme.Font)

	-- centre: crosshair, hitmarker, warnings ------------------------------------------
	local cross = Theme.frame(gui, "Crosshair", UDim2.new(0, 40, 0, 40), UDim2.new(0.5, -20, 0.5, -20), Theme.Bg, 1)
	refs.crossLines = {}
	for i, d in { { 0, -1 }, { 0, 1 }, { -1, 0 }, { 1, 0 } } do
		local l = Theme.frame(cross, "L" .. i, if d[1] == 0 then UDim2.new(0, 2, 0, 8) else UDim2.new(0, 8, 0, 2), UDim2.new(0.5, 0, 0.5, 0), Color3.new(1, 1, 1), 0.1)
		l.AnchorPoint = Vector2.new(0.5, 0.5)
		refs.crossLines[i] = { frame = l, d = d }
	end
	local dot = Theme.frame(cross, "Dot", UDim2.new(0, 2, 0, 2), UDim2.new(0.5, -1, 0.5, -1), Color3.new(1, 1, 1), 0.2)
	local _ = dot
	refs.cross = cross
	refs.hitmarker = Theme.label(gui, "Hitmarker", "X", UDim2.new(0, 30, 0, 30), UDim2.new(0.5, -15, 0.5, -15), 30, Color3.new(1, 1, 1), Theme.FontBold)
	refs.hitmarker.TextXAlignment = Enum.TextXAlignment.Center
	refs.hitmarker.TextTransparency = 1
	refs.protect = Theme.label(gui, "Protected", "SPAWN PROTECTION", UDim2.new(0, 300, 0, 20), UDim2.new(0.5, -150, 0.62, 0), 15, Theme.Good, Theme.FontBold)
	refs.protect.TextXAlignment = Enum.TextXAlignment.Center
	refs.protect.Visible = false
	refs.oob = Theme.label(gui, "OutOfBounds", "", UDim2.new(0, 700, 0, 40), UDim2.new(0.5, -350, 0.35, 0), 30, Theme.Warn, Theme.FontBlack)
	refs.oob.TextXAlignment = Enum.TextXAlignment.Center
	refs.oob.Visible = false
	-- damage vignette + direction
	refs.vignette = Theme.frame(gui, "Vignette", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), Color3.fromRGB(160, 0, 0), 1)
	local vg = Instance.new("UIGradient")
	vg.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.2), NumberSequenceKeypoint.new(0.5, 1), NumberSequenceKeypoint.new(1, 0.2) })
	vg.Parent = refs.vignette
	refs.vignette.ZIndex = 0
	refs.dmgArrow = Theme.label(gui, "DamageDir", "▲", UDim2.new(0, 40, 0, 40), UDim2.new(0.5, -20, 0.5, -20), 34, Theme.Red, Theme.FontBlack)
	refs.dmgArrow.TextXAlignment = Enum.TextXAlignment.Center
	refs.dmgArrow.TextTransparency = 1

	-- kill feed + notifications ------------------------------------------------------
	local feed = Theme.frame(gui, "KillFeed", UDim2.new(0, 380, 0, 200), UDim2.new(0, 16, 0, 16), Theme.Bg, 1)
	local fl = Instance.new("UIListLayout")
	fl.SortOrder = Enum.SortOrder.LayoutOrder
	fl.Padding = UDim.new(0, 3)
	fl.Parent = feed
	refs.feed = feed
	local notes = Theme.frame(gui, "Notifications", UDim2.new(0, 520, 0, 120), UDim2.new(0.5, -260, 0.3, 0), Theme.Bg, 1)
	local nl = Instance.new("UIListLayout")
	nl.SortOrder = Enum.SortOrder.LayoutOrder
	nl.HorizontalAlignment = Enum.HorizontalAlignment.Center
	nl.Padding = UDim.new(0, 4)
	nl.Parent = notes
	refs.notes = notes
	gui.Parent = player:WaitForChild("PlayerGui")
end

-- ---------------------------------------------------------------------------
-- Feeds
-- ---------------------------------------------------------------------------
local feedOrder = 0
function HUD.killfeed(e: { [string]: any })
	feedOrder += 1
	local row = Theme.frame(refs.feed, "Row", UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, 0), Theme.Panel, 0.35)
	row.LayoutOrder = feedOrder
	Theme.corner(row, 3)
	local text = Theme.label(row, "T", "", UDim2.new(1, -12, 1, 0), UDim2.new(0, 6, 0, 0), 14, Theme.Text, Theme.FontBold)
	text.RichText = true
	local function c(team: number?): string
		local col = Theme.team(team or 0)
		return string.format("#%02X%02X%02X", col.R * 255, col.G * 255, col.B * 255)
	end
	if e.kind == "kill" then
		text.Text = string.format('<font color="%s">%s</font>  [%s%s]  <font color="%s">%s</font>', c(e.killerTeam), e.killer or "World", e.weapon or "", if e.headshot then " HS" else "", c(e.victimTeam), e.victim or "?")
	elseif e.kind == "vehicleKill" then
		text.Text = string.format('<font color="%s">%s</font>  destroyed  <font color="%s">%s</font>', c(e.killerTeam), e.killer or "Unknown", c(e.team), e.vehicle or "vehicle")
	end
	local children = refs.feed:GetChildren()
	local rows = 0
	for _, ch in children do
		if ch:IsA("Frame") then
			rows += 1
		end
	end
	if rows > 7 then
		local oldest, lo = nil, math.huge
		for _, ch in children do
			if ch:IsA("Frame") and ch.LayoutOrder < lo then
				oldest, lo = ch, ch.LayoutOrder
			end
		end
		if oldest then
			oldest:Destroy()
		end
	end
	task.delay(8, function()
		if row.Parent then
			row:Destroy()
		end
	end)
end

local noteOrder = 0
function HUD.notify(text: string, color: Color3?)
	noteOrder += 1
	local l = Theme.label(refs.notes, "Note", text, UDim2.new(1, 0, 0, 30), UDim2.new(0, 0, 0, 0), 22, color or Theme.Text, Theme.FontBlack)
	l.TextXAlignment = Enum.TextXAlignment.Center
	l.TextStrokeTransparency = 0.5
	l.LayoutOrder = noteOrder
	task.delay(3.5, function()
		local tw = TweenService:Create(l, TweenInfo.new(0.6), { TextTransparency = 1, TextStrokeTransparency = 1 })
		tw:Play()
		tw.Completed:Wait()
		l:Destroy()
	end)
end

local function flashHit(isKill: boolean, head: boolean)
	local h = refs.hitmarker :: TextLabel
	h.TextColor3 = if isKill then Theme.Red elseif head then Theme.Gold else Color3.new(1, 1, 1)
	h.TextTransparency = 0
	TweenService:Create(h, TweenInfo.new(0.35), { TextTransparency = 1 }):Play()
end

local function showDamage(amount: number, from: Vector3?)
	local v = refs.vignette :: Frame
	v.BackgroundTransparency = math.clamp(0.85 - amount / 120, 0.35, 0.85)
	TweenService:Create(v, TweenInfo.new(0.8), { BackgroundTransparency = 1 }):Play()
	if from then
		local cam = workspace.CurrentCamera
		local rel = cam.CFrame:PointToObjectSpace(from)
		local ang = math.atan2(rel.X, -rel.Z)
		local a = refs.dmgArrow :: TextLabel
		a.Position = UDim2.new(0.5, math.sin(ang) * 120 - 20, 0.5, -math.cos(ang) * 120 - 20)
		a.Rotation = math.deg(ang)
		a.TextTransparency = 0
		TweenService:Create(a, TweenInfo.new(1.2), { TextTransparency = 1 }):Play()
	end
end

-- ---------------------------------------------------------------------------
-- Per-frame update
-- ---------------------------------------------------------------------------
local pulse = 0
local function N(name: string, d: number): number
	return Util.num(state, name, d)
end
local function S(name: string, d: string): string
	return Util.str(state, name, d)
end
local function update(dt: number)
	if not gui.Enabled then
		return
	end
	pulse += dt
	local victory = N("VictoryTicks", 10000)
	local rate = N("TickRate", 10)
	local function setTeam(r: any, ticks: number, held: number)
		local secs = math.floor(ticks / rate)
		r.timer.Text = string.format("%04d / %d SEC", secs, victory // rate)
		r.bar.Size = UDim2.new(math.clamp(ticks / victory, 0, 1), 0, 1, 0)
		r.held.Text = held .. (if held == 1 then " FLAG" else " FLAGS")
	end
	local blueHeld = N("BlueHeld", 0)
	local redHeld = N("RedHeld", 0)
	setTeam(refs.blue, N("BlueTicks", 0), blueHeld)
	setTeam(refs.red, N("RedTicks", 0), redHeld)
	refs.clock.Text = "MATCH " .. Util.formatTime((N("Tick", 0)) / rate)
	refs.flags.Text = string.format("CAPTURED  %d BLUE  |  %d RED", blueHeld, redHeld)
	refs.sudden.Visible = state:GetAttribute("SuddenDeath") == true

	local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	local inZone: string? = nil
	for _, id in POINT_IDS do
		local r = refs.points[id]
		local owner = N("P_" .. id .. "_Owner", 0)
		local progress = N("P_" .. id .. "_Progress", 0)
		local contested = state:GetAttribute("P_" .. id .. "_Contested") == true
		local capturing = N("P_" .. id .. "_Capturing", 0)
		r.badge.BackgroundColor3 = Theme.teamDark(owner)
		r.stroke.Color = if contested then Theme.Warn else Theme.team(owner)
		r.stroke.Thickness = if contested then 2 + math.abs(math.sin(pulse * 6)) * 2 else 2
		-- fill shows progress toward the side the meter is moving to
		local frac = math.abs(progress)
		r.fill.Size = UDim2.new(1, 0, frac, 0)
		r.fill.BackgroundColor3 = if progress >= 0 then Theme.Blue else Theme.Red
		r.fill.BackgroundTransparency = if owner ~= 0 and frac >= 0.999 then 0.05 else 0.35
		local blueN = N("P_" .. id .. "_Blue", 0)
		local redN = N("P_" .. id .. "_Red", 0)
		if contested then
			r.status.Text = "CONTESTED"
			r.status.TextColor3 = Theme.Warn
		elseif capturing ~= 0 then
			r.status.Text = string.format("%d%%", math.floor(frac * 100))
			r.status.TextColor3 = Theme.team(capturing)
		elseif owner ~= 0 then
			r.status.Text = Constants.TEAM_NAME[owner]
			r.status.TextColor3 = Theme.team(owner)
		else
			r.status.Text = "NEUTRAL"
			r.status.TextColor3 = Theme.TextDim
		end
		local _ = blueN + redN
		-- is the local player inside this zone?
		if root then
			local px, pz = N("P_" .. id .. "_X", 0), N("P_" .. id .. "_Z", 0)
			local rad = N("P_" .. id .. "_Radius", 100)
			if (Vector3.new(px, 0, pz) - root.Position * Vector3.new(1, 0, 1)).Magnitude < rad then
				inZone = id
			end
		end
	end
	-- capture panel
	local team = ClientState.team
	if inZone and ClientState.deployed then
		local owner = N("P_" .. inZone .. "_Owner", 0)
		local progress = N("P_" .. inZone .. "_Progress", 0)
		local contested = state:GetAttribute("P_" .. inZone .. "_Contested") == true
		local capturing = N("P_" .. inZone .. "_Capturing", 0)
		local name = S("P_" .. inZone .. "_Name", inZone)
		refs.capture.Visible = true
		local text
		if contested then
			text = "CONTESTED " .. inZone .. "  -  CLEAR THE ZONE"
		elseif capturing == team and owner ~= 0 and owner ~= team then
			text = "NEUTRALIZING " .. inZone
		elseif capturing == team then
			text = "CAPTURING " .. inZone
		elseif owner == team then
			text = "DEFENDING " .. inZone .. "  " .. name
		elseif capturing ~= 0 then
			text = "ENEMY CAPTURING " .. inZone
		else
			text = inZone .. "  " .. name
		end
		refs.capText.Text = text
		refs.capText.TextColor3 = if contested then Theme.Warn else Theme.team(if capturing ~= 0 then capturing else owner)
		refs.capBar.Size = UDim2.new(math.abs(progress), 0, 1, 0)
		refs.capBar.BackgroundColor3 = if progress >= 0 then Theme.Blue else Theme.Red
	else
		refs.capture.Visible = false
	end
	-- objective
	if ClientState.deployed and root then
		local bestId, bestD, bestKind = nil, math.huge, ""
		for _, id in POINT_IDS do
			local owner = N("P_" .. id .. "_Owner", 0)
			local contested = state:GetAttribute("P_" .. id .. "_Contested") == true
			local px, pz = N("P_" .. id .. "_X", 0), N("P_" .. id .. "_Z", 0)
			local d = (Vector3.new(px, 0, pz) - root.Position * Vector3.new(1, 0, 1)).Magnitude
			local kind = if owner == team then (if contested then "DEFEND" else "") else "CAPTURE"
			if kind ~= "" and d < bestD then
				bestId, bestD, bestKind = id, d, kind
			end
		end
		if bestId then
			refs.objective.Text = string.format("OBJECTIVE:  %s %s  -  %s   %d m", bestKind, bestId, S("P_" .. bestId .. "_Name", ""), math.floor(bestD / Constants.STUDS_PER_METER))
		else
			refs.objective.Text = "OBJECTIVE:  HOLD ALL THREE FLAGS"
		end
	else
		refs.objective.Text = ""
	end
	-- compass
	local cam = workspace.CurrentCamera
	local look = cam.CFrame.LookVector
	local heading = (math.deg(math.atan2(look.X, -look.Z)) + 360) % 360
	local width = refs.compass.AbsoluteSize.X
	local function place(label: TextLabel, deg: number, w: number)
		local diff = ((deg - heading + 540) % 360) - 180
		label.Visible = math.abs(diff) < 75
		label.Position = UDim2.new(0, width / 2 + diff / 75 * width / 2 - w / 2, 0, 0)
	end
	for _, m in refs.compassMarks do
		place(m.label, m.deg, 40)
	end
	for _, id in POINT_IDS do
		local l = refs.compassPoints[id]
		if root then
			local px, pz = N("P_" .. id .. "_X", 0), N("P_" .. id .. "_Z", 0)
			local d = Vector3.new(px - root.Position.X, 0, pz - root.Position.Z)
			local deg = (math.deg(math.atan2(d.X, -d.Z)) + 360) % 360
			place(l, deg, 60)
			local owner = N("P_" .. id .. "_Owner", 0)
			l.TextColor3 = Theme.team(owner)
			l.Text = string.format("%s %dm", id, math.floor(d.Magnitude / 3))
		else
			l.Visible = false
		end
	end
	-- player panel
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if hum then
		local hp = math.clamp(hum.Health / hum.MaxHealth, 0, 1)
		refs.hpBar.Size = UDim2.new(hp, 0, 1, 0)
		refs.hpBar.BackgroundColor3 = if hp > 0.5 then Theme.Good elseif hp > 0.25 then Theme.Warn else Theme.Red
		refs.hpText.Text = tostring(math.ceil(hum.Health))
	end
	refs.stBar.Size = UDim2.new(ClientState.stamina, 0, 1, 0)
	refs.faction.BackgroundColor3 = Theme.team(team)
	local role = Defs.Roles[ClientState.role]
	refs.roleText.Text = string.format("%s  -  %s", Constants.TEAM_ARMY[team] or "", if role then string.upper(role.name) else "")
	refs.roleText.TextColor3 = Theme.team(team)
	local vm = ClientState.vehicleModel
	if vm and vm.Parent then
		refs.vehicleRow.Visible = true
		local hpv = Util.num(vm, "HP", 0) / math.max(1, Util.num(vm, "MaxHP", 1))
		refs.vehicleName.Text = Defs.vehicleName(ClientState.vehicleKind or "", team) .. "  SEAT " .. tostring(ClientState.seat or 1)
		refs.vhBar.Size = UDim2.new(hpv, 0, 1, 0)
		refs.vhBar.BackgroundColor3 = if hpv > 0.5 then Theme.Good elseif hpv > 0.25 then Theme.Warn else Theme.Red
	else
		refs.vehicleRow.Visible = false
	end
	-- weapon panel
	refs.weaponName.Text = ClientState.weaponName
	if ClientState.vehicleId then
		refs.ammo.Text = if ClientState.vehicleReload < 1 then "RELOAD" else "READY"
		refs.ammo.TextSize = 30
		refs.reserve.Text = ""
	else
		refs.ammo.TextSize = 40
		refs.ammo.Text = tostring(ClientState.ammoMag)
		refs.reserve.Text = if ClientState.ammoReserve >= 0 then "/ " .. ClientState.ammoReserve else ""
		refs.ammo.TextColor3 = if ClientState.reloading then Theme.Warn elseif ClientState.ammoMag == 0 then Theme.Red else Theme.Text
	end
	-- crosshair spread
	local spread = 6 + ClientState.spread * 900
	for _, l in refs.crossLines do
		l.frame.Position = UDim2.new(0.5, l.d[1] * spread, 0.5, l.d[2] * spread)
	end
	refs.cross.Visible = not ClientState.aiming and ClientState.deployed
	-- warnings
	refs.protect.Visible = char ~= nil and char:GetAttribute("Protected") == true
	local oob = if char then char:GetAttribute("OutOfBounds") else nil
	if type(oob) == "number" then
		refs.oob.Visible = true
		refs.oob.Text = string.format("RETURN TO THE BATTLEFIELD  %d", math.ceil(oob))
	else
		refs.oob.Visible = false
	end
end

function HUD.setVisible(v: boolean)
	gui.Enabled = v
end

function HUD.init()
	state = Net.matchState()
	build()
	RunService.RenderStepped:Connect(update)
	ClientState.notify:Connect(function(text: string, color: Color3?)
		HUD.notify(text, color)
	end)
	ClientState.killfeed:Connect(function(e)
		HUD.killfeed(e)
	end)
	ClientState.hit:Connect(function(isKill: boolean, head: boolean)
		flashHit(isKill, head)
	end)
	ClientState.damaged:Connect(function(amount: number, from: Vector3?)
		showDamage(amount, from)
	end)
end

return HUD
