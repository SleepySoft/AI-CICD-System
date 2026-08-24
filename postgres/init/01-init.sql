-- AISystem 共享 PostgreSQL：为各服务预建数据库
-- 所有库归同一个超级用户（POSTGRES_USER）所有，内部环境简化处理

CREATE DATABASE keycloak;
CREATE DATABASE gitea;
CREATE DATABASE outline;
CREATE DATABASE openproject;
