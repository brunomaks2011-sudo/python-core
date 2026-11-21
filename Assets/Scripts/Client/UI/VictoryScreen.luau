--!strict
-- End of match: winning faction, final team timers, flags held, match
-- statistics, MVP and a restart button.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local Theme = require(script.Parent.Theme)
local ClientState = require(script.Parent.Parent.ClientState)

local VictoryScreen = {}

local player = Players.LocalPlayer
local gui: ScreenGui
local body: Frame
local restartLabel: TextButton
local state: Folder
VictoryScreen.onClosed = nil :: (() -> ())?

local function stat(parent: Instance, y: number, label: string, blue: string, red: string)
	Theme.label(parent, "L" .. y, label, UDim2.new(0.4, 0, 0, 24), UDim2.new(0.3, 0, 0, y), 15, Theme.TextDim, Theme.FontBold).TextXAlignment = Enum.TextXAlignment.Center
	local b = Theme.label(parent, "B" .. y, blue, UDim2.new(0.3, -10, 0, 24), UDim2.new(0, 0, 0, y), 17, Theme.Blue, Theme.FontBold)
	b.TextXAlignment = Enum.TextXAlignment.Right
	Theme.label(parent, "R" .. y, red, UDim2.new(0.3, -10, 0, 24), UDim2.new(0.7, 10, 0, y), 17, Theme.Red, Theme.FontBold)
end

function VictoryScreen.show(summary: { [string]: any })
	body:ClearAllChildren()
	gui.Enabled = true
	local winner = summary.winner or 0
	local mine = ClientState.team
	local banner = Theme.frame(body, "Banner", UDim2.new(1, 0, 0, 120), UDim2.new(0, 0, 0, 0), Theme.teamDark(winner), 0.05)
	Theme.corner(banner, 8)
	Theme.gradient(banner, Theme.team(winner), Theme.teamDark(winner), 0)
	local t = Theme.label(banner, "Title", string.upper(Constants.TEAM_ARMY[winner]) .. "  VICTORY", UDim2.new(1, 0, 0, 70), UDim2.new(0, 0, 0, 10), 54, Color3.new(1, 1, 1), Theme.FontBlack)
	t.TextXAlignment = Enum.TextXAlignment.Center
	local sub = Theme.label(banner, "Sub", if mine == 0 then "THREE FLAGS - DOMINATION" elseif mine == winner then "YOUR ARMY HELD THE VALLEY" else "YOUR ARMY WAS DEFEATED", UDim2.new(1, 0, 0, 30), UDim2.new(0, 0, 0, 78), 20, Color3.new(1, 1, 1), Theme.FontBold)
	sub.TextXAlignment = Enum.TextXAlignment.Center
	local stats = Theme.frame(body, "Stats", UDim2.new(1, 0, 0, 330), UDim2.new(0, 0, 0, 136), Theme.Panel, 0.15)
	Theme.corner(stats, 6)
	Theme.padding(stats, 14)
	Theme.label(stats, "BlueH", "BLUE ARMY", UDim2.new(0.3, -10, 0, 26), UDim2.new(0, 0, 0, 0), 20, Theme.Blue, Theme.FontBlack).TextXAlignment = Enum.TextXAlignment.Right
	Theme.label(stats, "RedH", "RED ARMY", UDim2.new(0.3, -10, 0, 26), UDim2.new(0.7, 10, 0, 0), 20, Theme.Red, Theme.FontBlack)
	local teams = summary.teams or {}
	local bt, rt = teams[1] or teams["1"] or {}, teams[2] or teams["2"] or {}
	stat(stats, 34, "CONTROL TIME", string.format("%d / 1000 s", math.floor(summary.blueSeconds or 0)), string.format("%d / 1000 s", math.floor(summary.redSeconds or 0)))
	stat(stats, 62, "FLAGS HELD AT THE END", tostring(summary.blueHeld or 0), tostring(summary.redHeld or 0))
	stat(stats, 90, "MOST FLAGS HELD AT ONCE", tostring(summary.maxHeldBlue or 0), tostring(summary.maxHeldRed or 0))
	stat(stats, 118, "ELIMINATIONS", tostring(bt.kills or 0), tostring(rt.kills or 0))
	stat(stats, 146, "LOSSES", tostring(bt.deaths or 0), tostring(rt.deaths or 0))
	stat(stats, 174, "FLAG CAPTURES", tostring(bt.captures or 0), tostring(rt.captures or 0))
	stat(stats, 202, "VEHICLES DESTROYED", tostring(bt.vehicleKills or 0), tostring(rt.vehicleKills or 0))
	local y = 234
	for _, id in { "A", "B", "C" } do
		local ps = summary.points and summary.points[id]
		if ps then
			stat(stats, y, "POINT " .. id .. " HELD (s)", tostring(ps.blueHeld), tostring(ps.redHeld))
			y += 26
		end
	end
	local footer = Theme.frame(body, "Footer", UDim2.new(1, 0, 0, 110), UDim2.new(0, 0, 0, 478), Theme.Bg, 1)
	local mvp = summary.mvp
	Theme.label(footer, "Duration", string.format("MATCH DURATION  %s     LEAD CHANGES  %d", Util.formatTime(summary.duration or 0), summary.leadChanges or 0), UDim2.new(1, 0, 0, 24), UDim2.new(0, 0, 0, 0), 16, Theme.Text, Theme.FontBold).TextXAlignment = Enum.TextXAlignment.Center
	if mvp then
		local l = Theme.label(footer, "MVP", string.format("MVP  %s  (%s)  -  %d pts, %d kills, %d captures", mvp.name, Constants.TEAM_ARMY[mvp.team] or "", mvp.score, mvp.kills, mvp.captures), UDim2.new(1, 0, 0, 24), UDim2.new(0, 0, 0, 28), 16, Theme.Gold, Theme.FontBold)
		l.TextXAlignment = Enum.TextXAlignment.Center
	end
	restartLabel = Theme.button(footer, "Restart", "RESTART MATCH", UDim2.new(0, 300, 0, 46), UDim2.new(0.5, -150, 0, 60), Theme.Gold)
	restartLabel.TextSize = 20
	restartLabel.MouseButton1Click:Connect(function()
		Net.event("RequestRestart"):FireServer()
		restartLabel.Text = "WAITING FOR VOTES..."
	end)
end

function VictoryScreen.hide()
	gui.Enabled = false
end

function VictoryScreen.init()
	state = Net.matchState()
	gui = Theme.screen("Victory", 40)
	gui.Enabled = false
	local shade = Theme.frame(gui, "Shade", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), Theme.Bg, 0.3)
	body = Theme.frame(shade, "Body", UDim2.new(0, 860, 0, 600), UDim2.new(0.5, -430, 0.5, -300), Theme.Bg, 1)
	gui.Parent = player:WaitForChild("PlayerGui")
	Net.event("MatchEvent").OnClientEvent:Connect(function(e)
		if type(e) ~= "table" then
			return
		end
		if e.kind == "victory" and type(e.summary) == "table" then
			VictoryScreen.show(e.summary)
		elseif e.kind == "restarted" then
			VictoryScreen.hide()
			if VictoryScreen.onClosed then
				VictoryScreen.onClosed()
			end
		end
	end)
	RunService.Heartbeat:Connect(function()
		if gui.Enabled and restartLabel and restartLabel.Parent then
			local s = Util.num(state, "RestartIn", 0)
			if restartLabel.Text ~= "WAITING FOR VOTES..." then
				restartLabel.Text = string.format("RESTART MATCH  (%d)", s)
			end
		end
	end)
	-- joined after the match ended
	if state:GetAttribute("State") == "ended" then
		task.spawn(function()
			local ok, summary = pcall(function()
				return Net.func("GetMatchSummary"):InvokeServer()
			end)
			if ok and type(summary) == "table" then
				VictoryScreen.show(summary)
			end
		end)
	end
end

return VictoryScreen
