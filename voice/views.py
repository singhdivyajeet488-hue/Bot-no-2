import discord
import datetime
from typing import Optional
from voice.controls import check_vc_ownership, apply_lock, apply_visibility, apply_user_override
from database import fetch_one, fetch_all

PANEL_COLOR = discord.Color.from_rgb(46, 139, 87) 

class VoiceLimitModal(discord.ui.Modal, title="Set Voice Channel User Limit"):
    limit_input = discord.ui.TextInput(label="User Limit (0-99, 0 for unlimited)", placeholder="Example: 5", max_length=2, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("You must be inside your active Voice Channel to apply configuration items.", ephemeral=True)
            return

        v_channel = member.voice.channel
        status, msg = check_vc_ownership(member.id, v_channel)  # type: ignore
        if not status:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        try:
            val = int(self.limit_input.value)
            if 0 <= val <= 99:
                await v_channel.edit(user_limit=val)
                await interaction.response.send_message(f"✅ Adjusted user cap parameter to `{val if val > 0 else 'Unlimited'}` successfully.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Limits must fall structurally between values 0 and 99.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid absolute raw integer provided.", ephemeral=True)

class VoiceRenameModal(discord.ui.Modal, title="Rename Voice Channel"):
    name_input = discord.ui.TextInput(label="New Channel Name", placeholder="My cool channel", max_length=50, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("You must be inside your active Voice Channel to apply configuration items.", ephemeral=True)
            return

        v_channel = member.voice.channel
        status, msg = check_vc_ownership(member.id, v_channel)  # type: ignore
        if not status:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        await v_channel.edit(name=self.name_input.value)
        await interaction.response.send_message(f"✅ Modified Voice Channel identity name string parameter to: `{self.name_input.value}`", ephemeral=True)

class VoiceDropdownSelector(discord.ui.Select):
    def __init__(self, select_type: str, voice_channel: discord.VoiceChannel):
        self.select_type = select_type
        self.voice_channel = voice_channel
        
        options = []
        if select_type == "KICK":
            for m in voice_channel.members:
                if m.id != voice_channel.guild.owner_id:
                    options.append(discord.SelectOption(label=m.display_name, value=str(m.id), description=f"Kick {m.name} from VC"))
            if not options:
                options.append(discord.SelectOption(label="No users available to target", value="none"))
                
        elif select_type == "BITRATE":
            max_br = int(voice_channel.guild.bitrate_limit)
            options = [
                discord.SelectOption(label="8 kbps (Low Quality)", value="8000"),
                discord.SelectOption(label="64 kbps (Standard Quality)", value="64000"),
                discord.SelectOption(label="96 kbps (High Quality)", value="96000")
            ]
            if max_br >= 128000:
                options.append(discord.SelectOption(label="128 kbps (HQ Audio)", value="128000"))
            if max_br >= 256000:
                options.append(discord.SelectOption(label="256 kbps (Premium Audio)", value="256000"))

        super().__init__(placeholder=f"Choose option for {select_type.lower()}...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Invalid Target Element Selection.", ephemeral=True)
            return
            
        member = interaction.user
        status, msg = check_vc_ownership(member.id, self.voice_channel)  # type: ignore
        if not status:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.select_type == "KICK":
            target_id = int(self.values[0])
            target = interaction.guild.get_member(target_id) # type: ignore
            if target and target in self.voice_channel.members:
                await target.move_to(None)
                await interaction.response.send_message(f"👢 Kicked {target.mention} out from the server voice instance.", ephemeral=True)
            else:
                await interaction.response.send_message("Target user has already exited the voice context session.", ephemeral=True)
                
        elif self.select_type == "BITRATE":
            br_val = int(self.values[0])
            if br_val <= int(interaction.guild.bitrate_limit): # type: ignore
                await self.voice_channel.edit(bitrate=br_val)
                await interaction.response.send_message(f"🔊 Modified audio session operational parameter bandwidth target to `{br_val // 1000} kbps`.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Selection exceeds server layout capabilities.", ephemeral=True)

class DropdownWrapperView(discord.ui.View):
    def __init__(self, select_type: str, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(VoiceDropdownSelector(select_type, voice_channel))

class VoiceControlPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    async def _resolve_context(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("❌ Error: You must connect to your temporary VC context to interact here.", ephemeral=True)
            return None
        
        v_channel = member.voice.channel
        status, msg = check_vc_ownership(member.id, v_channel) # type: ignore
        if not status:
            await interaction.response.send_message(msg, ephemeral=True)
            return None
            
        return v_channel # type: ignore

    @discord.ui.button(label="Lock VC", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="panel_lock")
    async def lock_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            await apply_lock(channel, True)
            await interaction.response.send_message("🔒 Session access secured. Unapproved users can no longer route entries.", ephemeral=True)

    @discord.ui.button(label="Unlock VC", style=discord.ButtonStyle.secondary, emoji="🔓", custom_id="panel_unlock")
    async def unlock_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            await apply_lock(channel, False)
            await interaction.response.send_message("🔓 Room entries unlocked safely for open connection access routing.", ephemeral=True)

    @discord.ui.button(label="Hide VC", style=discord.ButtonStyle.secondary, emoji="🙈", custom_id="panel_hide")
    async def hide_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            await apply_visibility(channel, True)
            await interaction.response.send_message("🙈 Visibility parameters updated. Channel is now hidden from the general server layout.", ephemeral=True)

    @discord.ui.button(label="Unhide VC", style=discord.ButtonStyle.secondary, emoji="👁", custom_id="panel_unhide")
    async def unhide_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            await apply_visibility(channel, False)
            await interaction.response.send_message("👁 Channel visibility restored across standard server structural trees.", ephemeral=True)

    @discord.ui.button(label="Kick User", style=discord.ButtonStyle.secondary, emoji="🚪", custom_id="panel_kick")
    async def kick_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            await interaction.response.send_message("Select a target user to kick from this session:", view=DropdownWrapperView("KICK", channel), ephemeral=True)

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.secondary, emoji="🚫", custom_id="panel_ban")
    async def ban_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            v = discord.ui.View(timeout=60)
            sel = discord.ui.UserSelect(placeholder="Select target user to access ban overrides...", max_values=1)
            
            async def ban_cb(i: discord.Interaction):
                target = sel.values[0]
                if isinstance(target, discord.Member):
                    await apply_user_override(channel, target, "BAN")
                    await i.response.send_message(f"🚫 Applied localized explicit restriction: `{target}` can no longer view or connect.", ephemeral=True)
                else:
                    await i.response.send_message("Selected entity cannot be verified natively.", ephemeral=True)
            
            sel.callback = ban_cb
            v.add_item(sel)
            await interaction.response.send_message("Choose target user context for localized explicit session lock ban:", view=v, ephemeral=True)

    @discord.ui.button(label="Permit User", style=discord.ButtonStyle.secondary, emoji="✅", custom_id="panel_permit")
    async def permit_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            v = discord.ui.View(timeout=60)
            sel = discord.ui.UserSelect(placeholder="Select user to explicitly permit/whitelist...", max_values=1)
            
            async def permit_cb(i: discord.Interaction):
                target = sel.values[0]
                if isinstance(target, discord.Member):
                    await apply_user_override(channel, target, "PERMIT")
                    await i.response.send_message(f"✅ User whitelisted: {target.mention} can now access your session.", ephemeral=True)
                else:
                    await i.response.send_message("Selected entity cannot be verified natively.", ephemeral=True)
            
            sel.callback = permit_cb
            v.add_item(sel)
            await interaction.response.send_message("Choose target user context to white-list:", view=v, ephemeral=True)

    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.secondary, emoji="👥", custom_id="panel_limit")
    async def limit_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("❌ Error: You must connect to your temporary VC context to interact here.", ephemeral=True)
            return
        status, msg = check_vc_ownership(member.id, member.voice.channel) # type: ignore
        if not status:
            await interaction.response.send_message(msg, ephemeral=True)
            return
            
        await interaction.response.send_modal(VoiceLimitModal())

    @discord.ui.button(label="Rename VC", style=discord.ButtonStyle.secondary, emoji="✏", custom_id="panel_rename")
    async def rename_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("❌ Error: You must connect to your temporary VC context to interact here.", ephemeral=True)
            return
        status, msg = check_vc_ownership(member.id, member.voice.channel) # type: ignore
        if not status:
            await interaction.response.send_message(msg, ephemeral=True)
            return
            
        await interaction.response.send_modal(VoiceRenameModal())

    @discord.ui.button(label="Bitrate", style=discord.ButtonStyle.secondary, emoji="🔊", custom_id="panel_bitrate")
    async def bitrate_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_context(interaction)
        if channel:
            await interaction.response.send_message("Select an audio encoding bitrate metric for tracking allocation changes:", view=DropdownWrapperView("BITRATE", channel), ephemeral=True)

    @discord.ui.button(label="VC Status", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="panel_status")
    async def status_vc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("❌ Error: You must be inside a channel to query local infrastructure data configurations.", ephemeral=True)
            return
            
        v_channel = member.voice.channel
        track = fetch_one("SELECT owner_id, creation_time FROM active_vcs WHERE channel_id = ?", (v_channel.id,))
        if not track:
            await interaction.response.send_message("This channel is not an active managed temporary voice instance.", ephemeral=True)
            return
            
        owner = interaction.guild.get_member(track[0]) or f"Unknown ID ({track[0]})" # type: ignore
        c_time = datetime.datetime.fromtimestamp(track[1]).strftime('%Y-%m-%d %H:%M:%S')
        
        embed = discord.Embed(title="📊 Session Status Overview", color=PANEL_COLOR)
        embed.add_field(name="Session Owner", value=getattr(owner, 'mention', str(owner)), inline=True)
        embed.add_field(name="Active User Payloads", value=f"`{len(v_channel.members)}` user(s)", inline=True)
        embed.add_field(name="Capacity Configurations Limit", value=f"`{v_channel.user_limit if v_channel.user_limit > 0 else 'Unlimited'}`", inline=True)
        embed.add_field(name="Session Bitrate Track", value=f"`{v_channel.bitrate // 1000} kbps`", inline=True)
        embed.add_field(name="Initialization Mark UTC", value=f"`{c_time}`", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

def generate_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Voice Channel Control Panel",
        description=(
            "Manage your temporary voice session channel options using the buttons below.\n\n"
            "🔒 **Lock VC** • Prevent new users joining\n"
            "🔓 **Unlock VC** • Allow joining again\n"
            "🙈 **Hide VC** • Hide channel from everyone\n"
            "👁 **Unhide VC** • Make channel visible again\n"
            "🚪 **Kick User** • Select user to disconnect\n"
            "🚫 **Ban User** • Prevent user from rejoining\n"
            "✅ **Permit User** • Whitelist user for room entry\n"
            "👥 **Set Limit** • Define session slot parameters\n"
            "📊 **VC Status** • Request current profile information metrics\n"
            "✏ **Rename VC** • Change session display criteria identifier\n"
            "🔊 **Bitrate** • Tune bandwidth performance allocations"
        ),
        color=PANEL_COLOR
    )
    embed.set_footer(text="Only verified session creators can change active settings configurations.")
    return embed
