from telegram import User

def user_id(user_id: int|User):
    if isinstance(user_id, User):
        return user_id.id

    return user_id

def mention_user(user: User):
    if user.username:
        return user.mention_html(user.username)
    else:
        return user.mention_html(user.first_name)