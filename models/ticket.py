"""Pydantic schemas and canonical constants (Contract v2.0)."""
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Section 4: Canonical Enums & Application Constants
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    """User roles specified in Section 4."""
    ORG_ADMIN = "Org_Admin"
    SUPPORT_AGENT = "Support_Agent"
    END_CUSTOMER = "End_Customer"


class TicketStatus(str, Enum):
    """Ticket statuses specified in Section 4."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    """Ticket priorities specified in Section 4."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, Enum):
    """Ticket categories specified in Section 4."""
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    GENERAL = "general"


class SenderType(str, Enum):
    """Sender types for ticket messages specified in Section 4."""
    CUSTOMER = "customer"
    SUPPORT_AGENT = "support_agent"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"


class InvoiceStatus(str, Enum):
    """Invoice statuses specified in Section 4."""
    PAID = "paid"
    PENDING = "pending"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class ApprovalStatus(str, Enum):
    """Approval statuses specified in Section 4."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Core Entities & Data Models
# ---------------------------------------------------------------------------

class TicketDetails(BaseModel):
    """Comprehensive representation of a multi-tenant support ticket compliant with Section 7 mapping."""
    ticket_id: int = Field(gt=0, description="Unique ticket identifier.")
    id: Optional[str] = Field(default=None, description="Deterministically generated UUID.")
    org_id: str = Field(..., description="Organization / tenant identifier UUID.")
    customer_id: str = Field(..., description="Customer user identifier UUID.")
    subject: str = Field(..., description="Headline of the customer issue.")
    title: Optional[str] = Field(default=None, description="Direct semantic mapping of subject.")
    description: str = Field(..., description="Detailed description of the problem.")
    status: TicketStatus = Field(..., description="Current status: open, in_progress, resolved, closed.")
    priority: TicketPriority = Field(..., description="Priority: low, medium, high, urgent.")
    category: TicketCategory = Field(default=TicketCategory.GENERAL, description="Category: billing, technical, account, general.")
    channel: Optional[str] = Field(default="web", description="Ticket Channel: chat, email, web, phone.")
    customer_email: Optional[str] = Field(default=None, description="Customer contact email.")
    customer_name: Optional[str] = Field(default=None, description="Full name of customer.")
    customer_age: Optional[int] = Field(default=None, description="Customer age demographic.")
    customer_gender: Optional[str] = Field(default=None, description="Customer gender demographic.")
    product_name: Optional[str] = Field(default=None, description="Billed product / ticket context.")
    invoice_id: Optional[str] = Field(default=None, description="Linked invoice ID if billing issue.")
    resolution: Optional[str] = Field(default=None, description="Resolution notes if resolved.")
    csat_rating: Optional[int] = Field(default=None, description="Customer satisfaction rating 1 to 5.")
    first_response_at: Optional[str] = Field(default=None, description="Event timestamp for live SLA calculation.")
    resolved_at: Optional[str] = Field(default=None, description="Event timestamp for live SLA calculation.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")
    updated_at: str = Field(..., description="ISO-8601 last update timestamp.")


class TicketMessage(BaseModel):
    """Public dialogue message inside a ticket (Section 6.B)."""
    message_id: str = Field(..., description="Unique message ID.")
    ticket_id: int = Field(..., description="Target ticket ID.")
    sender_type: SenderType = Field(..., description="customer, support_agent, ai_agent, system.")
    sender_id: Optional[str] = Field(default=None, description="Nullable user ID for AI-generated messages.")
    body: str = Field(..., min_length=1, description="Message body text.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")


class InternalNote(BaseModel):
    """Staff-only internal note (Section 6.C)."""
    note_id: str = Field(..., description="Unique note ID.")
    ticket_id: int = Field(..., description="Target ticket ID.")
    org_id: str = Field(..., description="Tenant org ID.")
    author_id: str = Field(..., description="Staff author user ID.")
    author_role: str = Field(..., description="Org_Admin or Support_Agent.")
    note: str = Field(..., min_length=1, max_length=5000, description="Internal note text.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")


class RefundAuditLog(BaseModel):
    """Refund transaction record (Section 6.D)."""
    refund_id: str = Field(..., description="Unique refund reference ID.")
    invoice_id: str = Field(..., description="Target invoice ID.")
    org_id: str = Field(..., description="Tenant org ID.")
    amount: float = Field(..., gt=0.0, description="Amount refunded.")
    reason: str = Field(..., description="Business rationale.")
    idempotency_key: str = Field(..., description="Unique request idempotency key.")
    approval_token: Optional[str] = Field(default=None, description="Admin approval token if amount > $100.")
    authorized_by: str = Field(..., description="Org_Admin user ID.")
    created_at: str = Field(..., description="ISO-8601 timestamp.")


# ---------------------------------------------------------------------------
# Tool Input Schemas
# ---------------------------------------------------------------------------

class CreateTicketInput(BaseModel):
    """Input parameters for creating a new support ticket."""
    subject: str = Field(..., min_length=3, description="Summary of the issue.")
    description: str = Field(..., min_length=5, description="Full explanation of the problem.")
    category: TicketCategory = Field(default=TicketCategory.GENERAL, description="billing, technical, account, general.")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="low, medium, high, urgent.")
    invoice_id: Optional[str] = Field(default=None, description="Optional linked invoice ID.")


class AddTicketMessageInput(BaseModel):
    """Input for posting a public dialogue message (Section 6.B)."""
    ticket_id: int = Field(gt=0, description="Target ticket ID.")
    body: str = Field(min_length=1, description="Message text content.")
    sender_type: SenderType = Field(default=SenderType.AI_AGENT, description="customer, support_agent, ai_agent, system.")
    sender_id: Optional[str] = Field(default=None, description="Sender ID (nullable for AI agent).")


class AddInternalNoteInput(BaseModel):
    """Input for staff-only whispers (Section 6.C)."""
    ticket_id: int = Field(gt=0, description="Target ticket ID.")
    note: str = Field(min_length=1, max_length=5000, description="Staff-only note content.")


class IssueRefundInput(BaseModel):
    """Input parameters for issuing a refund (Section 6.D)."""
    invoice_id: str = Field(..., description="Invoice ID to refund (e.g. 'inv_org_a_001').")
    amount: float = Field(..., gt=0.0, description="Refund amount in USD.")
    reason: str = Field(..., min_length=5, description="Business justification.")
    idempotency_key: str = Field(..., description="Unique client idempotency UUID.")
    approval_token: Optional[str] = Field(default=None, description="Required if amount > 100.00.")
    ticket_id: Optional[int] = Field(default=None, description="Optional associated ticket ID.")
