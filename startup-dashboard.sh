pip install streamlit plotly requests pandas
mkdir -p /home/site/wwwroot/.streamlit
cat > /home/site/wwwroot/.streamlit/config.toml << 'EOF'
[theme]
primaryColor        = "#1E3A5F"
backgroundColor     = "#FFFFFF"
secondaryBackgroundColor = "#F0F4F8"
textColor           = "#1A2636"
font                = "sans serif"

[server]
headless = true
EOF
streamlit run dashboard.py --server.port 8000 --server.address 0.0.0.0 --server.headless true
