# Splitwise SDK — API Reference

## Initialization

```python
# s is pre-initialized in repl.py — use it directly
# s = Splitwise(consumer_key, consumer_secret, api_key=api_key)
```

## Users

```python
me = s.getCurrentUser()
print(me.getId(), me.getFirstName(), me.getLastName(), me.getEmail())

user = s.getUser(user_id)
```

## Friends & Balances

```python
friends = s.getFriends()
for f in friends:
    print(f.getId(), f.getFirstName(), f.getLastName())
    for b in f.getBalances():
        print(" ", b.getCurrencyCode(), b.getAmount())
```

## Groups

```python
groups = s.getGroups()
for g in groups:
    print(g.getId(), g.getName())
    for m in g.getMembers():
        print(" member:", m.getFirstName(), m.getLastName())
    for b in g.getOriginalDebts():
        print(" debt:", b.getFromUser(), "->", b.getToUser(), b.getAmount(), b.getCurrencyCode())

group = s.getGroup(group_id)
```

## Expenses

```python
# List expenses (all optional filters)
expenses = s.getExpenses(
    offset=0,           # pagination offset
    limit=20,           # max results
    group_id=None,      # filter by group
    friend_id=None,     # filter by friend
    dated_after=None,   # "2024-01-01T00:00:00Z"
    dated_before=None,
    updated_after=None,
    updated_before=None,
)
for e in expenses:
    print(e.getId(), e.getDescription(), e.getCost(), e.getCurrencyCode(), e.getDate())
    for u in e.getUsers():
        print(" ", u.getId(), "paid:", u.getPaidShare(), "owed:", u.getOwedShare())

# Get single expense
expense = s.getExpense(expense_id)

# Create expense (equal split example)
from splitwise.expense import Expense
from splitwise.user import ExpenseUser

expense = Expense()
expense.setCost('20.00')
expense.setDescription('Dinner')
expense.setGroupId(group_id)         # optional

user1 = ExpenseUser()
user1.setId(my_user_id)
user1.setPaidShare('20.00')
user1.setOwedShare('10.00')

user2 = ExpenseUser()
user2.setId(friend_id)
user2.setPaidShare('0.00')
user2.setOwedShare('10.00')

expense.setUsers([user1, user2])
created, errors = s.createExpense(expense)
print(created.getId(), errors)

# Delete expense
s.deleteExpense(expense_id)
```

## Currencies & Categories

```python
currencies = s.getCurrencies()
for c in currencies:
    print(c.getCurrencyCode())

categories = s.getCategories()
for cat in categories:
    print(cat.getId(), cat.getName())
    for sub in cat.getSubcategories():
        print(" ", sub.getId(), sub.getName())
```

## Tips

- All object getters follow `getFieldName()` convention
- `createExpense` returns `(expense, errors)` — always check errors
- For equal splits, compute owed shares as `cost / num_users`
- Use `s.getCurrentUser().getId()` to get your own user ID before creating expenses
