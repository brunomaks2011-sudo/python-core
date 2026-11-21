--!strict
-- UI theme + small constructors used by every screen. Military-grade dark
-- glass panels; BLUE screens use blue accents, RED screens red accents.

local Theme = {}

Theme.Font = Enum.Font.GothamMedium
Theme.FontBold = Enum.Font.GothamBold
Theme.FontBlack = Enum.Font.GothamBlack
Theme.FontMono = Enum.Font.RobotoMono

Theme.Bg = Color3.fromRGB(10, 13, 17)
Theme.Panel = Color3.fromRGB(18, 22, 28)
Theme.PanelLight = Color3.fromRGB(30, 36, 44)
Theme.Line = Color3.fromRGB(70, 80, 92)
Theme.Text = Color3.fromRGB(232, 236, 240)
Theme.TextDim = Color3.fromRGB(150, 160, 172)
Theme.Neutral = Color3.fromRGB(205, 208, 214)
Theme.Blue = Color3.fromRGB(47, 123, 255)
Theme.BlueDark = Color3.fromRGB(16, 44, 104)
Theme.Red = Color3.fromRGB(255, 59, 48)
Theme.RedDark = Color3.fromRGB(104, 18, 14)
Theme.Gold = Color3.fromRGB(240, 196, 80)
Theme.Good = Color3.fromRGB(90, 210, 120)
Theme.Warn = Color3.fromRGB(255, 170, 40)

function Theme.team(team: number): Color3
	return if team == 1 then Theme.Blue elseif team == 2 then Theme.Red else Theme.Neutral
end

function Theme.teamDark(team: number): Color3
	return if team == 1 then Theme.BlueDark elseif team == 2 then Theme.RedDark else Theme.PanelLight
end

function Theme.frame(parent: Instance?, name: string, size: UDim2, pos: UDim2, color: Color3?, transparency: number?): Frame
	local f = Instance.new("Frame")
	f.Name = name
	f.Size = size
	f.Position = pos
	f.BackgroundColor3 = color or Theme.Panel
	f.BackgroundTransparency = transparency or 0
	f.BorderSizePixel = 0
	f.Parent = parent
	return f
end

function Theme.corner(parent: Instance, radius: number?)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius or 6)
	c.Parent = parent
	return c
end

function Theme.stroke(parent: Instance, color: Color3?, thickness: number?, transparency: number?)
	local s = Instance.new("UIStroke")
	s.Color = color or Theme.Line
	s.Thickness = thickness or 1
	s.Transparency = transparency or 0.3
	s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	s.Parent = parent
	return s
end

function Theme.padding(parent: Instance, px: number)
	local p = Instance.new("UIPadding")
	p.PaddingLeft = UDim.new(0, px)
	p.PaddingRight = UDim.new(0, px)
	p.PaddingTop = UDim.new(0, px)
	p.PaddingBottom = UDim.new(0, px)
	p.Parent = parent
	return p
end

function Theme.label(parent: Instance?, name: string, text: string, size: UDim2, pos: UDim2, textSize: number?, color: Color3?, font: Enum.Font?): TextLabel
	local l = Instance.new("TextLabel")
	l.Name = name
	l.Text = text
	l.Size = size
	l.Position = pos
	l.BackgroundTransparency = 1
	l.TextColor3 = color or Theme.Text
	l.Font = font or Theme.Font
	l.TextSize = textSize or 16
	l.TextXAlignment = Enum.TextXAlignment.Left
	l.TextYAlignment = Enum.TextYAlignment.Center
	l.Parent = parent
	return l
end

function Theme.button(parent: Instance?, name: string, text: string, size: UDim2, pos: UDim2, accent: Color3?): TextButton
	local b = Instance.new("TextButton")
	b.Name = name
	b.Text = text
	b.Size = size
	b.Position = pos
	b.AutoButtonColor = false
	b.BackgroundColor3 = Theme.PanelLight
	b.BackgroundTransparency = 0.15
	b.TextColor3 = Theme.Text
	b.Font = Theme.FontBold
	b.TextSize = 18
	b.BorderSizePixel = 0
	b.Parent = parent
	Theme.corner(b, 4)
	local stroke = Theme.stroke(b, accent or Theme.Line, 1, 0.4)
	local accentBar = Instance.new("Frame")
	accentBar.Name = "Accent"
	accentBar.Size = UDim2.new(0, 3, 1, 0)
	accentBar.BackgroundColor3 = accent or Theme.Gold
	accentBar.BorderSizePixel = 0
	accentBar.Visible = false
	accentBar.Parent = b
	b.MouseEnter:Connect(function()
		b.BackgroundColor3 = Theme.Line
		stroke.Transparency = 0
		accentBar.Visible = true
	end)
	b.MouseLeave:Connect(function()
		b.BackgroundColor3 = Theme.PanelLight
		stroke.Transparency = 0.4
		accentBar.Visible = false
	end)
	return b
end

function Theme.gradient(parent: Instance, a: Color3, b: Color3, rotation: number?)
	local g = Instance.new("UIGradient")
	g.Color = ColorSequence.new(a, b)
	g.Rotation = rotation or 90
	g.Parent = parent
	return g
end

function Theme.screen(name: string, order: number?): ScreenGui
	local g = Instance.new("ScreenGui")
	g.Name = name
	g.ResetOnSpawn = false
	g.IgnoreGuiInset = true
	g.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	g.DisplayOrder = order or 0
	return g
end

return Theme
