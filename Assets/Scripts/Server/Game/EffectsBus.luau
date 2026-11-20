--!strict
-- Batches visual/audio effect events (tracers, impacts, explosions, debris
-- bursts, glass, muzzle flashes...) and sends them to clients once per frame.

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Net = require(ReplicatedStorage.Shared.Net)

local EffectsBus = {}

local queue: { { [string]: any } } = {}
local remote: RemoteEvent? = nil

function EffectsBus.init()
	remote = Net.event("Effect")
	RunService.Heartbeat:Connect(function()
		if #queue == 0 or not remote then
			return
		end
		local batch = queue
		queue = {}
		-- split very large batches to stay well under remote payload limits
		local chunk = {}
		for _, e in batch do
			table.insert(chunk, e)
			if #chunk >= 120 then
				remote:FireAllClients(chunk)
				chunk = {}
			end
		end
		if #chunk > 0 then
			remote:FireAllClients(chunk)
		end
	end)
end

function EffectsBus.push(e: { [string]: any })
	table.insert(queue, e)
end

return EffectsBus
