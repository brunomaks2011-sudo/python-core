--!strict
-- Main menu: PLAY, MULTIPLAYER, SETTINGS, VEHICLE GARAGE, MAP SELECTION, EXIT.
-- (PvP only: there is no singleplayer mode against AI.) The live battlefield is visible behind it through a
-- slow aerial camera.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local SocialService = game:GetService("SocialService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Net = require(ReplicatedStorage.Shared.Net)
local Theme = require(script.Parent.Theme)
local ClientState = require(script.Parent.Parent.ClientState)

local MainMenu = {}

local player = Players.LocalPlayer
local gui: ScreenGui
local page: Frame
local refs: { [string]: any } = {}
local state: Folder
MainMenu.onPlay = nil :: (() -> ())?
local camAngle = 0
local menuCamConn: RBXScriptConnection? = nil

local function clearPage(title: string)
	page:ClearAllChildren()
	page.Visible = true
	Theme.padding(page, 24)
	Theme.label(page, "Title", title, UDim2.new(1, 0, 0, 36), UDim2.new(0, 0, 0, 0), 28, Theme.Text, Theme.FontBlack)
end

local function stepper(parent: Instance, y: number, label: string, getText: () -> string, onMinus: () -> (), onPlus: () -> ())
	Theme.label(parent, label, label, UDim2.new(0.5, 0, 0, 32), UDim2.new(0, 0, 0, y), 17, Theme.TextDim, Theme.FontBold)
	local value = Theme.label(parent, label .. "Value", getText(), UDim2.new(0, 200, 0, 32), UDim2.new(0.5, 40, 0, y), 18, Theme.Text, Theme.FontBold)
	value.TextXAlignment = Enum.TextXAlignment.Center
	local minus = Theme.button(parent, "Minus", "-", UDim2.new(0, 36, 0, 32), UDim2.new(0.5, 0, 0, y))
	local plus = Theme.button(parent, "Plus", "+", UDim2.new(0, 36, 0, 32), UDim2.new(0.5, 244, 0, y))
	minus.MouseButton1Click:Connect(function()
		onMinus()
		value.Text = getText()
	end)
	plus.MouseButton1Click:Connect(function()
		onPlus()
		value.Text = getText()
	end)
end

local function choice(parent: Instance, y: number, label: string, items: { string }, current: number, onPick: (number) -> ())
	Theme.label(parent, label, label, UDim2.new(0.3, 0, 0, 32), UDim2.new(0, 0, 0, y), 17, Theme.TextDim, Theme.FontBold)
	local buttons = {}
	for i, it in items do
		local b = Theme.button(parent, it, it, UDim2.new(0, 104, 0, 32), UDim2.new(0.3, (i - 1) * 110, 0, y))
		b.TextSize = 14
		b.TextColor3 = if i == current then Theme.Gold else Theme.Text
		buttons[i] = b
		b.MouseButton1Click:Connect(function()
			for j, bb in buttons do
				bb.TextColor3 = if j == i then Theme.Gold else Theme.Text
			end
			onPick(i)
		end)
	end
end

-- ---------------------------------------------------------------------------
-- Pages
-- ---------------------------------------------------------------------------
local function multiplayerPage()
	clearPage("MULTIPLAYER")
	local body = Theme.frame(page, "Body", UDim2.new(1, 0, 1, -60), UDim2.new(0, 0, 0, 50), Theme.Bg, 1)
	local text = Theme.label(body, "Info", "Every Roblox server of BLUE vs RED is a live multiplayer battle on a dedicated, authoritative server: match timers, flag ownership, capture progress, destruction and respawns are decided by the server and synchronised to everyone. Two armies of real players: pick a side on the deployment screen.", UDim2.new(1, 0, 0, 80), UDim2.new(0, 0, 0, 0), 15, Theme.TextDim, Theme.Font)
	text.TextWrapped = true
	text.TextYAlignment = Enum.TextYAlignment.Top
	Theme.label(body, "PlayersTitle", "PLAYERS ON THIS SERVER", UDim2.new(1, 0, 0, 24), UDim2.new(0, 0, 0, 90), 16, Theme.Text, Theme.FontBold)
	local y = 120
	for _, p in Players:GetPlayers() do
		local t = 0
		if p.Team and p.Team.Name == Constants.TEAM_OBJECT_NAME[1] then
			t = 1
		elseif p.Team and p.Team.Name == Constants.TEAM_OBJECT_NAME[2] then
			t = 2
		end
		Theme.label(body, "P", string.format("%s   -   %s", p.DisplayName, Constants.TEAM_ARMY[t]), UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, y), 15, Theme.team(t), Theme.Font)
		y += 24
	end
	local counts = { [1] = 0, [2] = 0 }
	for _, p in Players:GetPlayers() do
		for t = 1, 2 do
			if p.Team and p.Team.Name == Constants.TEAM_OBJECT_NAME[t] then
				counts[t] += 1
			end
		end
	end
	Theme.label(body, "Teams", string.format("%s: %d   |   %s: %d", Constants.TEAM_ARMY[1], counts[1], Constants.TEAM_ARMY[2], counts[2]), UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, y + 6), 15, Theme.TextDim, Theme.Font)
	local invite = Theme.button(body, "Invite", "INVITE FRIENDS", UDim2.new(0, 240, 0, 46), UDim2.new(0, 0, 0, y + 44), Theme.Blue)
	invite.MouseButton1Click:Connect(function()
		local ok, can = pcall(function()
			return SocialService:CanSendGameInviteAsync(player)
		end)
		if ok and can then
			pcall(function()
				SocialService:PromptGameInvite(player)
			end)
		else
			invite.Text = "INVITES UNAVAILABLE"
		end
	end)
	local join = Theme.button(body, "Join", "JOIN THE BATTLE", UDim2.new(0, 240, 0, 46), UDim2.new(0, 256, 0, y + 44), Theme.Gold)
	join.MouseButton1Click:Connect(function()
		if MainMenu.onPlay then
			MainMenu.onPlay()
		end
	end)
end

local function settingsPage()
	clearPage("SETTINGS")
	local s = ClientState.settings
	local body = Theme.frame(page, "Body", UDim2.new(1, 0, 1, -60), UDim2.new(0, 0, 0, 50), Theme.Bg, 1)
	stepper(body, 0, "MOUSE SENSITIVITY", function()
		return string.format("%.2f", s.sensitivity)
	end, function()
		s.sensitivity = math.max(0.05, s.sensitivity - 0.05)
	end, function()
		s.sensitivity = math.min(2, s.sensitivity + 0.05)
	end)
	stepper(body, 44, "AIM SENSITIVITY", function()
		return string.format("%.2f", s.adsSensitivity)
	end, function()
		s.adsSensitivity = math.max(0.1, s.adsSensitivity - 0.05)
	end, function()
		s.adsSensitivity = math.min(1.5, s.adsSensitivity + 0.05)
	end)
	stepper(body, 88, "FIELD OF VIEW", function()
		return tostring(s.fov)
	end, function()
		s.fov = math.max(60, s.fov - 5)
	end, function()
		s.fov = math.min(100, s.fov + 5)
	end)
	stepper(body, 132, "MASTER VOLUME", function()
		return string.format("%d%%", math.floor(s.masterVolume * 100 + 0.5))
	end, function()
		s.masterVolume = math.max(0, s.masterVolume - 0.1)
	end, function()
		s.masterVolume = math.min(1, s.masterVolume + 0.1)
	end)
	stepper(body, 176, "MUSIC VOLUME", function()
		return string.format("%d%%", math.floor(s.musicVolume * 100 + 0.5))
	end, function()
		s.musicVolume = math.max(0, s.musicVolume - 0.1)
	end, function()
		s.musicVolume = math.min(1, s.musicVolume + 0.1)
	end)
	choice(body, 224, "INVERT MOUSE Y", { "OFF", "ON" }, if s.invertY then 2 else 1, function(i)
		s.invertY = i == 2
	end)
	choice(body, 270, "EFFECTS QUALITY", { "LOW", "MEDIUM", "HIGH" }, if s.quality == "low" then 1 elseif s.quality == "medium" then 2 else 3, function(i)
		s.quality = ({ "low", "medium", "high" })[i]
		ClientState.changed:Fire("quality")
	end)
	choice(body, 316, "MINIMAP", { "ON", "OFF" }, if s.showMinimap then 1 else 2, function(i)
		s.showMinimap = i == 1
		ClientState.changed:Fire("minimap")
	end)
	local keys = Theme.label(body, "Keys", "WASD move  |  Shift sprint  |  C crouch  |  Z prone  |  Space jump  |  E enter/exit vehicle  |  F switch seat  |  1-4 weapons  |  R reload  |  G grenade  |  RMB aim  |  V first/third person  |  M map  |  Tab scoreboard  |  L lights  |  Q/E helicopter yaw", UDim2.new(1, 0, 0, 60), UDim2.new(0, 0, 0, 364), 13, Theme.TextDim, Theme.Font)
	keys.TextWrapped = true
end

local garageTeam = 1
local garageKind = "mbt"
local viewport: ViewportFrame? = nil
local viewModel: Model? = nil
local function showVehicle()
	if not viewport then
		return
	end
	if viewModel then
		viewModel:Destroy()
		viewModel = nil
	end
	local def = Defs.Vehicles[garageKind]
	local name = def.model[garageTeam]
	local template: Model? = nil
	for _, d in ReplicatedStorage.Assets.Models:GetDescendants() do
		if d:IsA("Model") and d.Name == name then
			template = d
			break
		end
	end
	if template then
		local m = template:Clone()
		m.Parent = viewport
		viewModel = m
	end
	local stats = refs.garageStats :: TextLabel
	local seats = #def.seats
	local weapons = {}
	for _, w in def.weapons do
		table.insert(weapons, w.name)
	end
	for _, sd in def.seats do
		if sd.weapons then
			for _, w in sd.weapons do
				if type(w) == "table" then
					table.insert(weapons, w.name)
				end
			end
		end
	end
	stats.Text = string.format("%s\n%s\n\nArmour: %d HP\nTop speed: %d km/h\nCrew / seats: %d\nWeapons: %s\n%s",
		string.upper(def.names[garageTeam]), def.category, def.hp, math.floor(def.maxSpeed / 3 * 3.6), seats,
		if #weapons > 0 then table.concat(weapons, ", ") else "none",
		if def.aura then ("Support: " .. def.aura.kind) else "")
end

local function garagePage()
	clearPage("VEHICLE GARAGE")
	local body = Theme.frame(page, "Body", UDim2.new(1, 0, 1, -60), UDim2.new(0, 0, 0, 50), Theme.Bg, 1)
	local list = Instance.new("ScrollingFrame")
	list.Size = UDim2.new(0, 230, 1, 0)
	list.BackgroundTransparency = 1
	list.BorderSizePixel = 0
	list.ScrollBarThickness = 4
	list.AutomaticCanvasSize = Enum.AutomaticSize.Y
	list.CanvasSize = UDim2.new()
	list.Parent = body
	local ll = Instance.new("UIListLayout")
	ll.Padding = UDim.new(0, 4)
	ll.Parent = list
	for _, kind in Defs.VehicleOrder do
		local b = Theme.button(list, kind, Defs.Vehicles[kind].category, UDim2.new(1, -8, 0, 32), UDim2.new(), Theme.Gold)
		b.TextSize = 13
		b.MouseButton1Click:Connect(function()
			garageKind = kind
			showVehicle()
		end)
	end
	local vp = Instance.new("ViewportFrame")
	vp.Size = UDim2.new(1, -250, 0.68, 0)
	vp.Position = UDim2.new(0, 245, 0, 0)
	vp.BackgroundColor3 = Color3.fromRGB(26, 30, 36)
	vp.Ambient = Color3.fromRGB(150, 150, 150)
	vp.LightColor = Color3.fromRGB(255, 248, 235)
	vp.LightDirection = Vector3.new(-1, -1.2, -0.6)
	vp.Parent = body
	Theme.corner(vp, 6)
	local cam = Instance.new("Camera")
	cam.FieldOfView = 40
	cam.Parent = vp
	vp.CurrentCamera = cam
	viewport = vp
	local stats = Theme.label(body, "Stats", "", UDim2.new(1, -250, 0.3, -10), UDim2.new(0, 245, 0.7, 0), 15, Theme.Text, Theme.Font)
	stats.TextWrapped = true
	stats.TextYAlignment = Enum.TextYAlignment.Top
	refs.garageStats = stats
	local blue = Theme.button(body, "Blue", "BLUE ARMY", UDim2.new(0, 120, 0, 30), UDim2.new(1, -250, 0, 8), Theme.Blue)
	local red = Theme.button(body, "Red", "RED ARMY", UDim2.new(0, 120, 0, 30), UDim2.new(1, -124, 0, 8), Theme.Red)
	blue.ZIndex = 5
	red.ZIndex = 5
	blue.MouseButton1Click:Connect(function()
		garageTeam = 1
		showVehicle()
	end)
	red.MouseButton1Click:Connect(function()
		garageTeam = 2
		showVehicle()
	end)
	showVehicle()
end

local function mapPage()
	clearPage("MAP SELECTION")
	local info = MapInfo.get()
	local body = Theme.frame(page, "Body", UDim2.new(1, 0, 1, -60), UDim2.new(0, 0, 0, 50), Theme.Bg, 1)
	local card = Theme.frame(body, "Card", UDim2.new(1, 0, 0, 200), UDim2.new(0, 0, 0, 0), Theme.PanelLight, 0.1)
	Theme.corner(card, 6)
	Theme.stroke(card, Theme.Gold, 2, 0.2)
	Theme.label(card, "Name", string.upper(info.name), UDim2.new(1, -20, 0, 34), UDim2.new(0, 14, 0, 10), 26, Theme.Gold, Theme.FontBlack)
	local d = Theme.label(card, "Desc", "A fictional Eastern European river valley, 2 x 2 km of playable ground: the Ironvale Works industrial complex (A), Dolyna village (B) and Garrison 41 military base (C), joined by a highway, a railway and three bridges over the river. Forests, wheat and sunflower fields, farms, ruins and defensive positions.", UDim2.new(1, -28, 0, 110), UDim2.new(0, 14, 0, 48), 14, Theme.TextDim, Theme.Font)
	d.TextWrapped = true
	d.TextYAlignment = Enum.TextYAlignment.Top
	Theme.label(card, "Mode", "MODE: THREE FLAGS - DOMINATION  (first to 1000 seconds)", UDim2.new(1, -20, 0, 22), UDim2.new(0, 14, 1, -32), 15, Theme.Text, Theme.FontBold)
	Theme.label(body, "Conditions", "BATTLE CONDITIONS (server owner)", UDim2.new(1, 0, 0, 24), UDim2.new(0, 0, 0, 214), 16, Theme.TextDim, Theme.FontBold)
	local presets = {
		{ name = "MORNING CLEAR", time = 7.5, weather = "clear" },
		{ name = "OVERCAST NOON", time = 13, weather = "cloudy" },
		{ name = "RAINY DUSK", time = 18.4, weather = "rain" },
		{ name = "NIGHT FOG", time = 23.2, weather = "fog" },
		{ name = "STORM", time = 15, weather = "storm" },
	}
	for i, p in presets do
		local b = Theme.button(body, p.name, p.name, UDim2.new(0, 170, 0, 40), UDim2.new(0, ((i - 1) % 3) * 180, 0, 244 + ((i - 1) // 3) * 48), Theme.Gold)
		b.TextSize = 14
		b.MouseButton1Click:Connect(function()
			Net.event("ChangeSettings"):FireServer({ time = p.time, weather = p.weather })
			b.TextColor3 = Theme.Gold
		end)
	end
	local play = Theme.button(body, "Play", "PLAY THIS MAP", UDim2.new(0, 260, 0, 50), UDim2.new(0, 0, 0, 360), Theme.Gold)
	play.TextSize = 20
	play.MouseButton1Click:Connect(function()
		if MainMenu.onPlay then
			MainMenu.onPlay()
		end
	end)
end

local function exitPage()
	clearPage("EXIT")
	local body = Theme.frame(page, "Body", UDim2.new(1, 0, 1, -60), UDim2.new(0, 0, 0, 50), Theme.Bg, 1)
	Theme.label(body, "Q", "Leave the battle?", UDim2.new(1, 0, 0, 30), UDim2.new(0, 0, 0, 0), 18, Theme.Text, Theme.FontBold)
	local yes = Theme.button(body, "Yes", "LEAVE GAME", UDim2.new(0, 200, 0, 46), UDim2.new(0, 0, 0, 50), Theme.Red)
	local no = Theme.button(body, "No", "STAY", UDim2.new(0, 200, 0, 46), UDim2.new(0, 214, 0, 50))
	yes.MouseButton1Click:Connect(function()
		player:Kick("Thanks for playing BLUE vs RED - Three Flags Domination.")
	end)
	no.MouseButton1Click:Connect(function()
		page.Visible = false
	end)
end

-- ---------------------------------------------------------------------------
-- Menu camera
-- ---------------------------------------------------------------------------
local function startMenuCamera()
	local cam = workspace.CurrentCamera
	cam.CameraType = Enum.CameraType.Scriptable
	local info = MapInfo.get()
	local centre = Vector3.new(info.points[2].x, info.points[2].y, info.points[2].z)
	menuCamConn = RunService.RenderStepped:Connect(function(dt)
		camAngle += dt * 0.025
		local pos = centre + Vector3.new(math.cos(camAngle) * 520, 170, math.sin(camAngle) * 520)
		cam.CFrame = CFrame.lookAt(pos, centre + Vector3.new(0, 20, 0))
		cam.FieldOfView = 60
		if viewport and viewModel and viewport.CurrentCamera then
			local _, size = viewModel:GetBoundingBox()
			local r = size.Magnitude * 0.85
			local c = viewModel:GetPivot().Position + Vector3.new(0, size.Y * 0.35, 0)
			viewport.CurrentCamera.CFrame = CFrame.lookAt(c + Vector3.new(math.cos(camAngle * 8) * r, r * 0.45, math.sin(camAngle * 8) * r), c)
		end
	end)
end

local function stopMenuCamera()
	if menuCamConn then
		menuCamConn:Disconnect()
		menuCamConn = nil
	end
end

-- ---------------------------------------------------------------------------
function MainMenu.open()
	ClientState.inMenu = true
	gui.Enabled = true
	page.Visible = false
	startMenuCamera()
end

function MainMenu.close()
	gui.Enabled = false
	stopMenuCamera()
end

function MainMenu.init()
	state = Net.matchState()
	gui = Theme.screen("MainMenu", 30)
	local shade = Theme.frame(gui, "Shade", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), Theme.Bg, 0.35)
	local g = Instance.new("UIGradient")
	g.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0), NumberSequenceKeypoint.new(0.45, 0.35), NumberSequenceKeypoint.new(1, 0.9) })
	g.Parent = shade
	local title = Theme.label(shade, "Title", "", UDim2.new(0, 600, 0, 80), UDim2.new(0, 60, 0, 60), 64, Theme.Text, Theme.FontBlack)
	title.RichText = true
	title.Text = '<font color="#2F7BFF">BLUE</font> <font color="#9AA3AE">vs</font> <font color="#FF3B30">RED</font>'
	Theme.label(shade, "Sub", "THREE FLAGS  -  DOMINATION", UDim2.new(0, 600, 0, 30), UDim2.new(0, 64, 0, 138), 22, Theme.TextDim, Theme.FontBold)
	local items = {
		{ label = "PLAY", fn = function()
			if MainMenu.onPlay then
				MainMenu.onPlay()
			end
		end },
		{ label = "MULTIPLAYER", fn = multiplayerPage },
		{ label = "SETTINGS", fn = settingsPage },
		{ label = "VEHICLE GARAGE", fn = garagePage },
		{ label = "MAP SELECTION", fn = mapPage },
		{ label = "EXIT", fn = exitPage },
	}
	for i, it in items do
		local b = Theme.button(shade, it.label, it.label, UDim2.new(0, 300, 0, 48), UDim2.new(0, 60, 0, 200 + (i - 1) * 56), if i == 1 then Theme.Gold else Theme.Line)
		b.TextXAlignment = Enum.TextXAlignment.Left
		b.TextSize = 22
		local pad = Instance.new("UIPadding")
		pad.PaddingLeft = UDim.new(0, 18)
		pad.Parent = b
		if i == 1 then
			b.BackgroundColor3 = Color3.fromRGB(60, 52, 30)
		end
		b.MouseButton1Click:Connect(it.fn)
	end
	page = Theme.frame(shade, "Page", UDim2.new(0, 680, 0, 520), UDim2.new(0, 400, 0, 200), Theme.Panel, 0.12)
	Theme.corner(page, 8)
	Theme.stroke(page, Theme.Line, 1, 0.3)
	page.Visible = false
	local footer = Theme.label(shade, "Footer", "", UDim2.new(0, 700, 0, 20), UDim2.new(0, 60, 1, -40), 13, Theme.TextDim, Theme.Font)
	RunService.Heartbeat:Connect(function()
		if gui.Enabled then
			footer.Text = string.format("%s  |  %d players  |  team vs team PvP", MapInfo.get().name, #Players:GetPlayers())
		end
	end)
	gui.Parent = player:WaitForChild("PlayerGui")
end

return MainMenu
