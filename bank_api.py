import random

def get_transactions(user_id):

    categories = ["Food","Travel","Shopping","Transport"]

    transactions = []

    for i in range(3):

        transactions.append({
            "amount": random.randint(100,500),
            "category": random.choice(categories),
            "date": "2026-03-07"
        })

    return transactions
