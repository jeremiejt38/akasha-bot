import discord


async def ensure_admin_category_access(guild, admin_id):
    category = discord.utils.get(guild.categories, name="Administration")
    if category is None:
        category = await guild.create_category("Administration")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    admin = guild.get_member(admin_id)
    if admin:
        overwrites[admin] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
        )
    bot_member = guild.me
    if bot_member:
        overwrites[bot_member] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            manage_channels=True,
        )
    await category.edit(overwrites=overwrites, reason="Managed Akasha administration access")
    for channel in category.channels:
        if not channel.permissions_synced:
            await channel.edit(sync_permissions=True, reason="Managed Akasha administration access")
    return category
