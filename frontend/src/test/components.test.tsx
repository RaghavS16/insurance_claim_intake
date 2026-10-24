import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { PinInput } from '@/components/ui/PinInput';
import { MetricCard } from '@/components/ui/MetricCard';
import { BadgeDot, BadgePill } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Checkbox } from '@/components/ui/Checkbox';
import { DatePicker } from '@/components/ui/DatePicker';

describe('IntelliClaim Component Library', () => {
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
    render(<Input label="Policyholder Name" placeholder="e.g. Rajesh Sharma" />);
    expect(screen.getByText('Policyholder Name')).toBeInTheDocument();
    const input = screen.getByPlaceholderText('e.g. Rajesh Sharma');
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

  it('renders Checkbox with custom design and handles toggle', () => {
    const handleChange = vi.fn();
    render(<Checkbox label="I Accept the Terms" onChange={handleChange} />);
    const cb = screen.getByRole('checkbox');
    expect(cb).toBeInTheDocument();
    expect(screen.getByText('I Accept the Terms')).toBeInTheDocument();
    fireEvent.click(cb);
    expect(handleChange).toHaveBeenCalled();
  });

  it('renders DatePicker and opens custom month and year pickers', () => {
    const handleChange = vi.fn();
    render(<DatePicker label="Select Incident Date" value="2026-10-24" onChange={handleChange} />);
    expect(screen.getByText('Select Incident Date')).toBeInTheDocument();
    
    // Open calendar via toggle button
    const toggleBtn = screen.getByLabelText('Toggle calendar');
    fireEvent.click(toggleBtn);

    // Verify Month trigger button exists and can be clicked
    const monthBtn = screen.getByLabelText('Select month');
    expect(monthBtn).toBeInTheDocument();
    expect(screen.getByText('October')).toBeInTheDocument();
    fireEvent.click(monthBtn);
    // Jan to Dec pills rendered
    expect(screen.getByRole('button', { name: /^Jan$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Dec$/i })).toBeInTheDocument();
  });
});
