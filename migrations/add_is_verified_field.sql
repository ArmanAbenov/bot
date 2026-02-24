-- Migration: Add is_verified field to users table
-- Date: 2026-02-13
-- Description: Adds is_verified field for invite code security gate

-- Add is_verified column (default False for existing users)
ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0;

-- Set existing users as verified (they're already in the system)
UPDATE users SET is_verified = 1;

-- Verify migration
SELECT COUNT(*) as total_users, SUM(is_verified) as verified_users FROM users;
