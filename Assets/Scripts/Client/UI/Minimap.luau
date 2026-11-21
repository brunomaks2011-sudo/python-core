--!strict
-- Map widget drawn from the map data (roads, river, rail, buildings, fields,
-- forests, control points, HQs) plus live markers from the server's Radar feed.
-- Used as the corner minimap (player-centred, north-up) and as the full map
-- inside the deploy screen / M key.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Net = require(ReplicatedStorage.Shared.Net)
local Theme = require(script.Parent.Theme)
local ClientState = require(script.Parent.Parent.ClientState)

local Minimap = {}
Minimap.__index = Minimap

local player = Players.LocalPlayer
local radar: { [string]: any } = { s = {}, v = {}, e = {}, ev = {} }
local state: Folder

local function line(parent: Instance, a: Vector2, b: Vector2, width: number, color: Color3, transparency: number?): Frame
	local d = b - a
	local f = Instance.new("Frame")
	f.BorderSizePixel = 0
	f.BackgroundColor3 = color
	f.BackgroundTransparency = transparency or 0
	f.AnchorPoint = Vector2.new(0.5, 0.5)
	f.Size = UDim2.fromOffset(d.Magnitude + width * 0.5, width)
	f.Position = UDim2.fromOffset((a.X + b.X) / 2, (a.Y + b.Y) / 2)
	f.Rotation = math.deg(math.atan2(d.Y, d.X))
	f.Parent = parent
	return f
end

local function simplify(pts: { Vector2 }, tol: number): { Vector2 }
	if #pts < 3 then
		return pts
	end
	local out = { pts[1] }
	local last = pts[1]
	for i = 2, #pts - 1 do
		local p, nxt = pts[i], pts[i + 1]
		local a = (p - last).Unit
		local b = (nxt - p).Unit
		if a:Dot(b) < 0.995 or (p - last).Magnitude > 600 then
			table.insert(out, p)
			last = p
		end
		local _ = tol
	end
	table.insert(out, pts[#pts])
	return out
end

-- Build the static map layer into `canvas` at `scale` pixels per stud.
local function drawStatic(canvas: Frame, scale: number, extent: number)
	local info = MapInfo.get()
	local function px(x: number, z: number): Vector2
		return Vector2.new((x + extent) * scale, (z + extent) * scale)
	end
	canvas.BackgroundColor3 = Color3.fromRGB(64, 78, 52)
	-- forests from vegetation density
	local veg = MapInfo.vegetation()
	if veg then
		local cell = 96
		local n = math.ceil(extent * 2 / cell)
		local counts = {}
		for _, t in veg.trees do
			local i = math.floor((t.x + extent) / cell)
			local j = math.floor((t.z + extent) / cell)
			if i >= 0 and j >= 0 and i < n and j < n then
				local k = j * n + i
				counts[k] = (counts[k] or 0) + 1
			end
		end
		for k, c in counts do
			if c >= 5 then
				local i, j = k % n, k // n
				local f = Instance.new("Frame")
				f.BorderSizePixel = 0
				f.BackgroundColor3 = Color3.fromRGB(38, 56, 34)
				f.BackgroundTransparency = math.clamp(0.7 - c / 40, 0.15, 0.6)
				f.Size = UDim2.fromOffset(cell * scale + 1, cell * scale + 1)
				f.Position = UDim2.fromOffset(i * cell * scale, j * cell * scale)
				f.Parent = canvas
			end
		end
	end
	-- fields
	for _, fs in info.fields do
		local p = fs.poly
		local a, b, c = px(p[1][1], p[1][2]), px(p[2][1], p[2][2]), px(p[3][1], p[3][2])
		local d = px(p[4][1], p[4][2])
		local centre = (a + b + c + d) / 4
		local w = (b - a).Magnitude
		local h = (c - b).Magnitude
		local f = Instance.new("Frame")
		f.BorderSizePixel = 0
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		f.BackgroundColor3 = if fs.crop == "wheat" then Color3.fromRGB(150, 132, 72) elseif fs.crop == "plowed" or fs.crop == "sunflower" then Color3.fromRGB(96, 78, 56) else Color3.fromRGB(80, 102, 58)
		f.Size = UDim2.fromOffset(w, h)
		f.Position = UDim2.fromOffset(centre.X, centre.Y)
		f.Rotation = math.deg(math.atan2((b - a).Y, (b - a).X))
		f.BackgroundTransparency = 0.15
		f.Parent = canvas
	end
	-- river
	local river = {}
	for _, p in info.river.pts do
		table.insert(river, px(p[1], p[2]))
	end
	river = simplify(river, 2)
	for i = 1, #river - 1 do
		line(canvas, river[i], river[i + 1], math.max(2, info.river.width * scale), Color3.fromRGB(58, 98, 128))
	end
	-- rail
	local rail = {}
	for _, p in info.rail.pts do
		table.insert(rail, px(p[1], p[3]))
	end
	rail = simplify(rail, 2)
	for i = 1, #rail - 1 do
		line(canvas, rail[i], rail[i + 1], 2, Color3.fromRGB(110, 92, 78))
	end
	-- roads
	for _, road in info.roads do
		local pts = {}
		for _, p in road.pts do
			table.insert(pts, px(p[1], p[3]))
		end
		pts = simplify(pts, 2)
		local col = if road.kind == "dirt" then Color3.fromRGB(150, 128, 92) else Color3.fromRGB(190, 190, 184)
		local w = math.max(1.5, road.width * scale * (if road.kind == "highway" then 1.2 else 1))
		for i = 1, #pts - 1 do
			line(canvas, pts[i], pts[i + 1], w, col)
		end
	end
	-- buildings
	for _, b in info.buildings do
		local f = Instance.new("Frame")
		f.BorderSizePixel = 0
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		f.BackgroundColor3 = if (b.preDamage or 0) >= 3 then Color3.fromRGB(96, 86, 78) else Color3.fromRGB(196, 190, 178)
		local c = px(b.x, b.z)
		f.Size = UDim2.fromOffset(math.max(2, b.W * scale), math.max(2, b.D * scale))
		f.Position = UDim2.fromOffset(c.X, c.Y)
		f.Rotation = -math.deg(b.yaw)
		f.Parent = canvas
	end
	-- HQs
	for _, h in info.hqs do
		local c = px(h.x, h.z)
		local f = Instance.new("Frame")
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		f.Size = UDim2.fromOffset(h.radius * 2 * scale, h.radius * 2 * scale)
		f.Position = UDim2.fromOffset(c.X, c.Y)
		f.BackgroundColor3 = Theme.team(h.team)
		f.BackgroundTransparency = 0.7
		Theme.corner(f, 999)
		Theme.stroke(f, Theme.team(h.team), 2, 0)
		f.Parent = canvas
		local l = Theme.label(f, "L", "HQ", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), 12, Color3.new(1, 1, 1), Theme.FontBlack)
		l.TextXAlignment = Enum.TextXAlignment.Center
	end
end

export type Minimap = {
	root: Frame,
	clip: Frame,
	canvas: Frame,
	markers: Frame,
	scale: number,
	extent: number,
	follow: boolean,
	pointMarkers: { [string]: Frame },
	pool: { Frame },
	onClick: ((x: number, z: number) -> ())?,
}

function Minimap.new(parent: Instance, size: UDim2, pos: UDim2, scale: number, follow: boolean)
	local info = MapInfo.get()
	local extent = math.max(info.playable.maxX, info.playable.maxZ) + 300
	local root = Theme.frame(parent, "Minimap", size, pos, Theme.Panel, 0.1)
	Theme.corner(root, if follow then 999 else 6)
	Theme.stroke(root, Theme.Line, 2, 0.2)
	local clip = Theme.frame(root, "Clip", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), Theme.Bg, 1)
	clip.ClipsDescendants = true
	Theme.corner(clip, if follow then 999 else 6)
	local canvas = Theme.frame(clip, "Canvas", UDim2.fromOffset(extent * 2 * scale, extent * 2 * scale), UDim2.fromOffset(0, 0), Color3.fromRGB(64, 78, 52), 0)
	drawStatic(canvas, scale, extent)
	local markers = Theme.frame(canvas, "Markers", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), Theme.Bg, 1)
	markers.ZIndex = 5
	local self = setmetatable({
		root = root, clip = clip, canvas = canvas, markers = markers, scale = scale, extent = extent, follow = follow,
		pointMarkers = {}, pool = {}, onClick = nil,
	}, Minimap)
	for _, p in info.points do
		local f = Theme.frame(markers, "Point" .. p.id, UDim2.fromOffset(math.max(18, p.radius * 2 * scale), math.max(18, p.radius * 2 * scale)), UDim2.fromOffset((p.x + extent) * scale, (p.z + extent) * scale), Theme.Neutral, 0.45)
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		Theme.corner(f, 999)
		Theme.stroke(f, Color3.new(1, 1, 1), 2, 0.2)
		local l = Theme.label(f, "L", p.id, UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), 14, Color3.new(1, 1, 1), Theme.FontBlack)
		l.TextXAlignment = Enum.TextXAlignment.Center
		f.ZIndex = 6
		l.ZIndex = 7
		self.pointMarkers[p.id] = f
	end
	if not follow then
		local click = Instance.new("TextButton")
		click.Text = ""
		click.BackgroundTransparency = 1
		click.Size = UDim2.fromScale(1, 1)
		click.ZIndex = 4
		click.Parent = canvas
		click.MouseButton1Click:Connect(function()
			local m = game:GetService("UserInputService"):GetMouseLocation()
			local rel = Vector2.new(m.X, m.Y - 0) - canvas.AbsolutePosition
			local x = rel.X / scale - extent
			local z = rel.Y / scale - extent
			if self.onClick then
				self.onClick(x, z)
			end
		end)
	end
	return self
end

function Minimap.toCanvas(self: any, x: number, z: number): UDim2
	return UDim2.fromOffset((x + self.extent) * self.scale, (z + self.extent) * self.scale)
end

local function marker(self: any, i: number): Frame
	local f = self.pool[i]
	if not f then
		f = Instance.new("Frame")
		f.BorderSizePixel = 0
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		f.ZIndex = 8
		Theme.corner(f, 999)
		f.Parent = self.markers
		self.pool[i] = f
	end
	f.Visible = true
	return f
end

function Minimap.update(self: any)
	local team = ClientState.team
	local n = 0
	local function put(x: number, z: number, color: Color3, size: number, square: boolean?)
		n += 1
		local f = marker(self, n)
		f.Position = self:toCanvas(x, z)
		f.Size = UDim2.fromOffset(size, size)
		f.BackgroundColor3 = color
		local corner = f:FindFirstChildOfClass("UICorner")
		if corner then
			corner.CornerRadius = UDim.new(0, if square then 2 else 999)
		end
	end
	local myId = player:GetAttribute("SoldierId")
	for _, s in radar.s do
		if s[4] ~= myId and s[5] == 0 then
			put(s[1], s[2], Theme.team(team), 6)
		end
	end
	for _, v in radar.v do
		put(v[1], v[2], Theme.team(team):Lerp(Color3.new(1, 1, 1), 0.3), 10, true)
	end
	local enemy = if team == 1 then 2 else 1
	for _, e in radar.e do
		put(e[1], e[2], Theme.team(enemy), 7)
	end
	for _, v in radar.ev do
		put(v[1], v[2], Theme.team(enemy):Lerp(Color3.new(1, 1, 1), 0.2), 11, true)
	end
	for i = n + 1, #self.pool do
		self.pool[i].Visible = false
	end
	-- point colours
	for id, f in self.pointMarkers do
		local owner = state:GetAttribute("P_" .. id .. "_Owner") or 0
		local contested = state:GetAttribute("P_" .. id .. "_Contested") == true
		f.BackgroundColor3 = if contested then Theme.Warn else Theme.team(owner)
	end
	-- self arrow + follow
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
	if root then
		n += 1
		local me = marker(self, n)
		me.Position = self:toCanvas(root.Position.X, root.Position.Z)
		me.Size = UDim2.fromOffset(10, 10)
		me.BackgroundColor3 = Theme.Gold
		if self.follow then
			local c = self.clip.AbsoluteSize
			self.canvas.Position = UDim2.fromOffset(c.X / 2 - (root.Position.X + self.extent) * self.scale, c.Y / 2 - (root.Position.Z + self.extent) * self.scale)
		end
	end
end

function Minimap.init()
	state = Net.matchState()
	Net.unreliable("Radar").OnClientEvent:Connect(function(packet)
		if type(packet) == "table" then
			radar = packet
		end
	end)
	local _ = RunService
end

return Minimap
