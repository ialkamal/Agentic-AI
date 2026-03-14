flowchart TD
A[Customer Request] --> B[Orchestrator]

    B --> C[InventoryAgent]
    B --> D[QuotingAgent]
    B --> E[OrderingAgent]

    C --> C1[Tool: inventory_snapshot_tool<br/>uses get_all_inventory]
    C --> C2[Tool: stock_check_tool<br/>uses get_stock_level]
    C --> C3[Tool: supplier_eta_tool<br/>uses get_supplier_delivery_date]
    C --> C4[Tool: financial_health_tool<br/>uses get_cash_balance + generate_financial_report]

    D --> D1[Tool: quote_history_tool<br/>uses search_quote_history]
    D --> D2[Tool: stock_check_tool<br/>uses get_stock_level]
    D --> D3[Tool: financial_health_tool<br/>uses get_cash_balance + generate_financial_report]

    E --> E1[Tool: create_sale_tool<br/>uses create_transaction]
    E --> E2[Tool: create_stock_order_tool<br/>uses create_transaction]
    E --> E3[Tool: stock_check_tool<br/>uses get_stock_level]

    C --> B
    D --> B
    B --> E
    E --> F[Customer Response]
