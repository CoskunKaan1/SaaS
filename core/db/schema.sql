/* =====================================================================
   Şirket İçi API Kredi Takip Sistemi — Microsoft SQL Server şeması
   ---------------------------------------------------------------------
   Betik idempotenttir: tekrar çalıştırıldığında var olan nesnelere
   dokunmaz. Uygulama açılışında core/db/migrate.py tarafından "GO"
   satırlarından bölünerek sırayla çalıştırılır. SSMS'te de doğrudan
   çalıştırılabilir.
   ===================================================================== */

/* 1) Departmanlar ---------------------------------------------------- */
IF OBJECT_ID(N'dbo.Departments', N'U') IS NULL
CREATE TABLE dbo.Departments (
    DepartmentId  INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Departments PRIMARY KEY,
    Name          NVARCHAR(100)     NOT NULL CONSTRAINT UQ_Departments_Name UNIQUE,
    CostCenter    VARCHAR(20)       NOT NULL,
    CreatedAt     DATETIME2(0)      NOT NULL CONSTRAINT DF_Departments_CreatedAt DEFAULT SYSDATETIME()
);
GO

/* 2) Ekipler --------------------------------------------------------- */
IF OBJECT_ID(N'dbo.Teams', N'U') IS NULL
CREATE TABLE dbo.Teams (
    TeamId        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Teams PRIMARY KEY,
    DepartmentId  INT               NOT NULL CONSTRAINT FK_Teams_Departments
                                    REFERENCES dbo.Departments(DepartmentId),
    Name          NVARCHAR(100)     NOT NULL,
    CreatedAt     DATETIME2(0)      NOT NULL CONSTRAINT DF_Teams_CreatedAt DEFAULT SYSDATETIME(),
    CONSTRAINT UQ_Teams_Department_Name UNIQUE (DepartmentId, Name)
);
GO

/* 3) Kullanıcılar ---------------------------------------------------- */
IF OBJECT_ID(N'dbo.Users', N'U') IS NULL
CREATE TABLE dbo.Users (
    UserId        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Users PRIMARY KEY,
    TeamId        INT               NOT NULL CONSTRAINT FK_Users_Teams
                                    REFERENCES dbo.Teams(TeamId),
    FullName      NVARCHAR(120)     NOT NULL,
    Email         NVARCHAR(160)     NOT NULL CONSTRAINT UQ_Users_Email UNIQUE,
    Role          VARCHAR(20)       NOT NULL CONSTRAINT DF_Users_Role DEFAULT 'member'
                                    CONSTRAINT CK_Users_Role CHECK (Role IN ('member','lead','admin','service')),
    IsSimulated   BIT               NOT NULL CONSTRAINT DF_Users_IsSimulated DEFAULT 0,
    IsActive      BIT               NOT NULL CONSTRAINT DF_Users_IsActive DEFAULT 1,
    CreatedAt     DATETIME2(0)      NOT NULL CONSTRAINT DF_Users_CreatedAt DEFAULT SYSDATETIME()
);
GO

/* 4) API sağlayıcıları (harici / dahili) ------------------------------ */
IF OBJECT_ID(N'dbo.ApiProviders', N'U') IS NULL
CREATE TABLE dbo.ApiProviders (
    ProviderId    INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ApiProviders PRIMARY KEY,
    Name          NVARCHAR(100)     NOT NULL CONSTRAINT UQ_ApiProviders_Name UNIQUE,
    Kind          VARCHAR(10)       NOT NULL CONSTRAINT CK_ApiProviders_Kind CHECK (Kind IN ('external','internal'))
);
GO

/* 5) API servisleri ve birim fiyatları ------------------------------- */
IF OBJECT_ID(N'dbo.ApiServices', N'U') IS NULL
CREATE TABLE dbo.ApiServices (
    ServiceId     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ApiServices PRIMARY KEY,
    ProviderId    INT               NOT NULL CONSTRAINT FK_ApiServices_Providers
                                    REFERENCES dbo.ApiProviders(ProviderId),
    Name          NVARCHAR(100)     NOT NULL,
    UnitName      NVARCHAR(20)      NOT NULL,
    CreditPerUnit DECIMAL(12,4)     NOT NULL CONSTRAINT CK_ApiServices_Price CHECK (CreditPerUnit > 0),
    IsActive      BIT               NOT NULL CONSTRAINT DF_ApiServices_IsActive DEFAULT 1,
    CONSTRAINT UQ_ApiServices_Provider_Name UNIQUE (ProviderId, Name)
);
GO

/* 6) Ekip ↔ servis erişim izni (M:N) --------------------------------- */
IF OBJECT_ID(N'dbo.TeamServiceAccess', N'U') IS NULL
CREATE TABLE dbo.TeamServiceAccess (
    TeamId        INT          NOT NULL CONSTRAINT FK_TSA_Teams    REFERENCES dbo.Teams(TeamId),
    ServiceId     INT          NOT NULL CONSTRAINT FK_TSA_Services REFERENCES dbo.ApiServices(ServiceId),
    GrantedAt     DATETIME2(0) NOT NULL CONSTRAINT DF_TSA_GrantedAt DEFAULT SYSDATETIME(),
    CONSTRAINT PK_TeamServiceAccess PRIMARY KEY (TeamId, ServiceId)
);
GO

/* 7) Ekip bütçe dönemleri ---------------------------------------------
   Her ekibin aynı anda yalnızca bir açık (ClosedAt IS NULL) dönemi olur.
   "Sıfırlama" açık dönemi kapatıp aynı limitle yeni bir dönem açar;
   böylece geçmiş harcama silinmez, raporlanabilir kalır.               */
IF OBJECT_ID(N'dbo.TeamBudgets', N'U') IS NULL
CREATE TABLE dbo.TeamBudgets (
    TeamBudgetId  INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TeamBudgets PRIMARY KEY,
    TeamId        INT               NOT NULL CONSTRAINT FK_TeamBudgets_Teams
                                    REFERENCES dbo.Teams(TeamId),
    CreditLimit   DECIMAL(14,2)     NOT NULL CONSTRAINT CK_TeamBudgets_Limit CHECK (CreditLimit > 0),
    WarnPercent   TINYINT           NOT NULL CONSTRAINT DF_TeamBudgets_Warn DEFAULT 80
                                    CONSTRAINT CK_TeamBudgets_Warn CHECK (WarnPercent BETWEEN 1 AND 99),
    StartedAt     DATETIME2(0)      NOT NULL CONSTRAINT DF_TeamBudgets_StartedAt DEFAULT SYSDATETIME(),
    ClosedAt      DATETIME2(0)      NULL,
    CloseReason   NVARCHAR(120)     NULL,
    CONSTRAINT CK_TeamBudgets_Dates CHECK (ClosedAt IS NULL OR ClosedAt >= StartedAt)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TeamBudgets_OneActive')
CREATE UNIQUE INDEX UX_TeamBudgets_OneActive ON dbo.TeamBudgets(TeamId) WHERE ClosedAt IS NULL;
GO

/* 8) Kullanım kayıtları (her API çağrısı bir satır) ------------------- */
IF OBJECT_ID(N'dbo.UsageRecords', N'U') IS NULL
CREATE TABLE dbo.UsageRecords (
    UsageId        BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_UsageRecords PRIMARY KEY,
    TeamBudgetId   INT              NOT NULL CONSTRAINT FK_Usage_TeamBudgets REFERENCES dbo.TeamBudgets(TeamBudgetId),
    UserId         INT              NOT NULL CONSTRAINT FK_Usage_Users       REFERENCES dbo.Users(UserId),
    ServiceId      INT              NOT NULL CONSTRAINT FK_Usage_Services    REFERENCES dbo.ApiServices(ServiceId),
    Units          INT              NOT NULL CONSTRAINT CK_Usage_Units CHECK (Units > 0),
    CreditsCharged DECIMAL(14,4)    NOT NULL CONSTRAINT CK_Usage_Credits CHECK (CreditsCharged >= 0),
    StatusCode     SMALLINT         NOT NULL,
    LatencyMs      INT              NOT NULL,
    Outcome        VARCHAR(10)      NOT NULL CONSTRAINT CK_Usage_Outcome CHECK (Outcome IN ('ok','error','rejected')),
    CreatedAt      DATETIME2(3)     NOT NULL CONSTRAINT DF_Usage_CreatedAt DEFAULT SYSDATETIME()
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Usage_Budget')
CREATE INDEX IX_Usage_Budget ON dbo.UsageRecords(TeamBudgetId) INCLUDE (CreditsCharged, Outcome);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Usage_CreatedAt')
CREATE INDEX IX_Usage_CreatedAt ON dbo.UsageRecords(CreatedAt) INCLUDE (CreditsCharged, ServiceId, Outcome);
GO

/* 9) Bildirimler ----------------------------------------------------- */
IF OBJECT_ID(N'dbo.Notifications', N'U') IS NULL
CREATE TABLE dbo.Notifications (
    NotificationId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Notifications PRIMARY KEY,
    TeamId         INT              NULL CONSTRAINT FK_Notifications_Teams REFERENCES dbo.Teams(TeamId),
    Severity       VARCHAR(10)      NOT NULL CONSTRAINT CK_Notifications_Severity
                                    CHECK (Severity IN ('info','warning','critical')),
    Title          NVARCHAR(150)    NOT NULL,
    Body           NVARCHAR(500)    NOT NULL,
    IsRead         BIT              NOT NULL CONSTRAINT DF_Notifications_IsRead DEFAULT 0,
    CreatedAt      DATETIME2(0)     NOT NULL CONSTRAINT DF_Notifications_CreatedAt DEFAULT SYSDATETIME()
);
GO

/* 10) Test kullanıcılarının simülasyon davranışı (1:1 Users) ---------- */
IF OBJECT_ID(N'dbo.SimulationProfiles', N'U') IS NULL
CREATE TABLE dbo.SimulationProfiles (
    UserId         INT          NOT NULL CONSTRAINT PK_SimulationProfiles PRIMARY KEY
                                CONSTRAINT FK_SimProfiles_Users REFERENCES dbo.Users(UserId) ON DELETE CASCADE,
    Persona        VARCHAR(20)  NOT NULL CONSTRAINT CK_SimProfiles_Persona
                                CHECK (Persona IN ('steady','bursty','heavy','wave')),
    CallsPerMinute INT          NOT NULL CONSTRAINT CK_SimProfiles_Rate CHECK (CallsPerMinute BETWEEN 1 AND 600),
    ErrorRate      DECIMAL(4,3) NOT NULL CONSTRAINT DF_SimProfiles_Error DEFAULT 0.02
                                CONSTRAINT CK_SimProfiles_Error CHECK (ErrorRate BETWEEN 0 AND 1),
    IsEnabled      BIT          NOT NULL CONSTRAINT DF_SimProfiles_Enabled DEFAULT 1
);
GO

/* ---------------------------------------------------------------------
   Görünüm: ekiplerin açık dönemdeki bütçe durumu
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW dbo.vw_TeamBudgetStatus AS
SELECT  b.TeamBudgetId,
        t.TeamId,
        t.Name                       AS TeamName,
        d.Name                       AS DepartmentName,
        b.CreditLimit,
        b.WarnPercent,
        b.StartedAt,
        ISNULL(SUM(u.CreditsCharged), 0)                              AS Spent,
        COUNT(CASE WHEN u.Outcome <> 'rejected' THEN 1 END)           AS Calls,
        COUNT(CASE WHEN u.Outcome =  'rejected' THEN 1 END)           AS Rejected
FROM    dbo.TeamBudgets b
JOIN    dbo.Teams        t ON t.TeamId       = b.TeamId
JOIN    dbo.Departments  d ON d.DepartmentId = t.DepartmentId
LEFT JOIN dbo.UsageRecords u ON u.TeamBudgetId = b.TeamBudgetId
WHERE   b.ClosedAt IS NULL
GROUP BY b.TeamBudgetId, t.TeamId, t.Name, d.Name, b.CreditLimit, b.WarnPercent, b.StartedAt;
GO

/* ---------------------------------------------------------------------
   Saklı yordam: ekibin açık dönemini kapatıp yenisini aç (sıfırlama)
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_ResetTeamBudget
    @TeamId INT,
    @Reason NVARCHAR(120)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRANSACTION;

    DECLARE @Limit DECIMAL(14,2), @Warn TINYINT;

    SELECT @Limit = CreditLimit, @Warn = WarnPercent
    FROM   dbo.TeamBudgets WITH (UPDLOCK, HOLDLOCK)
    WHERE  TeamId = @TeamId AND ClosedAt IS NULL;

    IF @Limit IS NULL
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 50001, N'Ekibin açık bütçe dönemi yok.', 1;
    END

    UPDATE dbo.TeamBudgets
    SET    ClosedAt = SYSDATETIME(), CloseReason = @Reason
    WHERE  TeamId = @TeamId AND ClosedAt IS NULL;

    INSERT INTO dbo.TeamBudgets (TeamId, CreditLimit, WarnPercent)
    VALUES (@TeamId, @Limit, @Warn);

    SELECT CAST(SCOPE_IDENTITY() AS INT) AS NewTeamBudgetId;
    COMMIT TRANSACTION;
END;
GO
