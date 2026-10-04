class UserDirectoryRow(tuple):
    """Seven visible user fields plus a hidden identifier for row actions."""

    def __new__(cls, values, user_id=None):
        row = super().__new__(cls, values)
        row.user_id = user_id
        return row
