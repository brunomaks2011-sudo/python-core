--!strict
-- Scoreboard (hold Tab): both armies side by side - name, class, eliminations,
-- deaths, assists, captured points, time spent defending objectives, score.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local Theme = require(script.Parent.Theme)

local Scoreboard = {}

local player = Players.LocalPlayer
local gui: ScreenGui
local columns: { [number]: ScrollingFrame } = {}
local open = false
local COLS = {
	{ name = "NAME", w = 0.34 }, { name = "CLASS", w = 0.14 }, { name = "K", w = 0.07 }, { name = "D", w = 0.07 },
	{ name = "A", w = 0.07 }, { name = "CAP", w = 0.08 }, { name = "DEF", w = 0.1 }, { name = "SCORE", w = 0.13 },
}

local function header(parent: Instance, team: number)
	local h = Theme.frame(parent, "Header", UDim2.new(1, 0, 0, 30), UDim2.new(0, 0, 0, 0), Theme.teamDark(team), 0.05)
	local x = 0
	for _, c in COLS do
		local l = Theme.label(h, c.name, c.name, UDim2.new(c.w, -4, 1, 0), UDim2.new(x, 6, 0, 0), 13, Theme.Text, Theme.FontBlack)
		local _ = l
		x += c.w
	end
end

local function build()
	gui = Theme.screen("Scoreboard", 25)
	gui.Enabled = false
	local bg = Theme.frame(gui, "Bg", UDim2.new(0, 1180, 0, 600), UDim2.new(0.5, -590, 0.5, -300), Theme.Bg, 0.15)
	Theme.corner(bg, 8)
	Theme.padding(bg, 14)
	for i, team in { 1, 2 } do
		local col = Theme.frame(bg, "Team" .. team, UDim2.new(0.5, -8, 1, 0), UDim2.new((i - 1) * 0.5, (i - 1) * 8, 0, 0), Theme.Panel, 0.2)
		Theme.corner(col, 6)
		Theme.label(col, "Title", if team == 1 then "BLUE ARMY" else "RED ARMY", UDim2.new(1, -12, 0, 30), UDim2.new(0, 10, 0, 2), 20, Theme.team(team), Theme.FontBlack)
		local body = Theme.frame(col, "Body", UDim2.new(1, 0, 1, -36), UDim2.new(0, 0, 0, 36), Theme.Bg, 1)
		header(body, team)
		local list = Instance.new("ScrollingFrame")
		list.Size = UDim2.new(1, 0, 1, -34)
		list.Position = UDim2.new(0, 0, 0, 34)
		list.BackgroundTransparency = 1
		list.BorderSizePixel = 0
		list.ScrollBarThickness = 3
		list.AutomaticCanvasSize = Enum.AutomaticSize.Y
		list.CanvasSize = UDim2.new()
		list.Parent = body
		local ll = Instance.new("UIListLayout")
		ll.SortOrder = Enum.SortOrder.LayoutOrder
		ll.Padding = UDim.new(0, 2)
		ll.Parent = list
		columns[team] = list
	end
	gui.Parent = player:WaitForChild("PlayerGui")
end

local function refresh()
	local ok, rows = pcall(function()
		return Net.func("GetScoreboard"):InvokeServer()
	end)
	if not ok or type(rows) ~= "table" then
		return
	end
	for _, list in columns do
		for _, ch in list:GetChildren() do
			if ch:IsA("Frame") then
				ch:Destroy()
			end
		end
	end
	local myId = player:GetAttribute("SoldierId")
	for i, r in rows do
		local list = columns[r.team]
		if not list then
			continue
		end
		local row = Theme.frame(list, "Row", UDim2.new(1, -6, 0, 24), UDim2.new(), if r.id == myId then Color3.fromRGB(70, 62, 30) else Theme.PanelLight, if r.id == myId then 0.1 else 0.5)
		row.LayoutOrder = i
		local vals = {
			(if r.id == myId then "> " else "") .. r.name .. (if r.alive then "" else "  (KIA)"),
			(Defs.Roles[r.role] and Defs.Roles[r.role].name) or r.role,
			tostring(r.kills), tostring(r.deaths), tostring(r.assists), tostring(r.captures), Util.formatTime(r.defend), tostring(r.score),
		}
		local x = 0
		for c, colDef in COLS do
			local l = Theme.label(row, colDef.name, vals[c], UDim2.new(colDef.w, -4, 1, 0), UDim2.new(x, 6, 0, 0), 13, if r.alive then Theme.Text else Theme.TextDim, if c == 1 then Theme.FontBold else Theme.Font)
			l.TextTruncate = Enum.TextTruncate.AtEnd
			x += colDef.w
		end
	end
end

function Scoreboard.init()
	build()
	UserInputService.InputBegan:Connect(function(input, processed)
		if input.KeyCode == Enum.KeyCode.Tab then
			open = true
			gui.Enabled = true
			refresh()
			task.spawn(function()
				while open do
					task.wait(1)
					if open then
						refresh()
					end
				end
			end)
		end
		local _ = processed
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.KeyCode == Enum.KeyCode.Tab then
			open = false
			gui.Enabled = false
		end
	end)
end

return Scoreboard
