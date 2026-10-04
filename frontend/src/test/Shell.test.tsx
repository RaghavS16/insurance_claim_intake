import {describe,expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Shell from '../components/Shell';

describe('Shell role navigation',()=>{
  it('exposes claim tracking to claimants',()=>{
    render(<MemoryRouter><Shell user={{role:'CLAIMANT',full_name:'Claimant'}}/></MemoryRouter>);
    expect(screen.getByRole('link',{name:/Track Claims/i})).toBeInTheDocument();
    expect(screen.getByRole('link',{name:/Claim Intake/i})).toBeInTheDocument();
    expect(screen.getByRole('link',{name:/Voice Intake/i})).toBeInTheDocument();
  });
  it('exposes queue and knowledge management to adjusters',()=>{
    render(<MemoryRouter><Shell user={{role:'ADJUSTER',full_name:'Adjuster'}}/></MemoryRouter>);
    expect(screen.getByRole('link',{name:/Claims Queue/i})).toBeInTheDocument();
    expect(screen.getByRole('link',{name:/Manage Knowledge/i})).toBeInTheDocument();
  });
});