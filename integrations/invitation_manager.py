"""Admin invitation manager for Wizarr.

Provides an interactive command to list and revoke Wizarr invitations.
"""
import logging
import discord
from discord import ui

logger = logging.getLogger(__name__)


class InvitationManager:
    def __init__(self, wizarr_client):
        self.wizarr_client = wizarr_client

    async def list_invitations(self, status: str | None = None):
        data = await self.wizarr_client.get_invitations()
        invitations = data.get("invitations", [])
        if status:
            invitations = [inv for inv in invitations if inv.get("status") == status]
        return invitations

    async def revoke_invitation(self, invitation_id: int):
        return await self.wizarr_client.delete_invitation(invitation_id)

    def format_invitation(self, inv: dict) -> str:
        code = inv.get("code", "N/A")
        status = inv.get("status", "N/A")
        used_by = inv.get("used_by") or "Non utilisé"
        expires = inv.get("expires") or "N/A"
        duration = inv.get("duration") or "N/A"
        return (
            f"`{code}` — **{status}**\n"
            f"Utilisé par: {used_by}\n"
            f"Expire: {expires} — Durée: {duration}"
        )


class RevokeButton(ui.Button):
    def __init__(self, invitation_id: int, code: str):
        super().__init__(
            label="Révoquer",
            style=discord.ButtonStyle.danger,
            custom_id=f"invitation:revoke:{invitation_id}",
        )
        self.invitation_id = invitation_id
        self.code = code

    async def callback(self, interaction: discord.Interaction):
        manager: InvitationManager = self.view.manager
        try:
            await manager.revoke_invitation(self.invitation_id)
            await interaction.response.edit_message(
                content=f"✅ Invitation `{self.code}` révoquée.",
                embed=None,
                view=None,
            )
        except Exception:
            logger.exception("Failed to revoke invitation %s", self.invitation_id)
            await interaction.response.send_message(
                f"❌ Impossible de révoquer l'invitation `{self.code}`.", ephemeral=True
            )


class InvitationsView(ui.View):
    def __init__(self, manager: InvitationManager, invitations: list):
        super().__init__(timeout=300)
        self.manager = manager
        for inv in invitations[:10]:
            self.add_item(RevokeButton(inv.get("id"), inv.get("code")))
