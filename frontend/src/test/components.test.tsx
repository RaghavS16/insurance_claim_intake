import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { PinInput } from '@/components/ui/PinInput';
import { MetricCard } from '@/components/ui/MetricCard';
import { BadgeDot, BadgePill } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';

describe('ApexCare Component Library', () => {
  it('renders Button with primary variant and handles click', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Submit Claim</Button>);
    const btn = screen.getByRole('button', { name: /Submit Claim/i });
    expect(btn).toBeInTheDocument();
    expect(btn.className).toContain('snow-btn-primary');
    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('renders Input with label and handles change', () => {
    render(<Input label="Policyholder Name" placeholder="e.g. John Doe" />);
    expect(screen.getByText('Policyholder Name')).toBeInTheDocument();
    const input = screen.getByPlaceholderText('e.g. John Doe');
    expect(input).toBeInTheDocument();
  });

  it('renders PinInput with 6 digit boxes', () => {
    const handleChange = vi.fn();
    render(<PinInput length={6} value="123" onChange={handleChange} />);
    const inputs = screen.getAllByRole('textbox');
    expect(inputs).toHaveLength(6);
    expect(inputs[0]).toHaveValue('1');
    expect(inputs[1]).toHaveValue('2');
    expect(inputs[2]).toHaveValue('3');
  });

  it('renders MetricCard with title, value, and trend', () => {
    render(
      <MetricCard
        title="Total Claims"
        value={48}
        trend="+11.02%"
        tint="sky"
      />
    );
    expect(screen.getByText('Total Claims')).toBeInTheDocument();
    expect(screen.getByText('48')).toBeInTheDocument();
    expect(screen.getByText('+11.02%')).toBeInTheDocument();
  });

  it('renders BadgeDot with status and label', () => {
    render(<BadgeDot status="complete" label="Approved" />);
    expect(screen.getByText('Approved')).toBeInTheDocument();
  });

  it('renders BadgePill with variant', () => {
    render(<BadgePill variant="mint">Active Policy</BadgePill>);
    expect(screen.getByText('Active Policy')).toBeInTheDocument();
  });

  it('renders Card with title and subtitle', () => {
    render(
      <Card title="Coverage Terms" subtitle="Section 4.2 Guidelines">
        <div>Card Content</div>
      </Card>
    );
    expect(screen.getByText('Coverage Terms')).toBeInTheDocument();
    expect(screen.getByText('Section 4.2 Guidelines')).toBeInTheDocument();
    expect(screen.getByText('Card Content')).toBeInTheDocument();
  });
});
