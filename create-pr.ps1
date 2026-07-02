$env:GITHUB_TOKEN="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"
& 'E:\gh.exe' pr create --base main --head data-management-feature --title 'fix: 修复patients路由+批次筛选' --body '修复GET /api/audio/patients路由缺失装饰器bug，新增批次筛选功能'
